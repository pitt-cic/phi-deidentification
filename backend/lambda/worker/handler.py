import asyncio
import json
import os
import random
import time

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.batch import BatchProcessor, EventType, process_partial_response
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

from agent import AgentResponse, DetectionParameters
from deidentification import process_document
from deidentification.redaction import find_pii_positions, redact_text

logger = Logger(service="pii_deidentification.worker")
processor = BatchProcessor(event_type=EventType.SQS)

s3_client = boto3.client("s3")
BUCKET_NAME = os.environ["BUCKET_NAME"]

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRYABLE_ERROR_CODE_SUBSTRINGS = ("throttl", "toomanyrequests", "serviceunavailable")
RETRYABLE_MESSAGE_SUBSTRINGS = ("too many tokens", "rate exceeded", "temporarily unavailable")


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
        return max(parsed, minimum)
    except ValueError:
        logger.warning("Invalid %s value '%s'; using default %d", name, raw_value, default)
        return default


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value)
        return max(parsed, minimum)
    except ValueError:
        logger.warning("Invalid %s value '%s'; using default %.2f", name, raw_value, default)
        return default


MODEL_RETRY_MAX_ATTEMPTS = _int_env("MODEL_RETRY_MAX_ATTEMPTS", default=4)
MODEL_RETRY_BASE_SECONDS = _float_env("MODEL_RETRY_BASE_SECONDS", default=1.0, minimum=0.1)
MODEL_RETRY_MAX_SECONDS = _float_env("MODEL_RETRY_MAX_SECONDS", default=16.0, minimum=MODEL_RETRY_BASE_SECONDS)
MODEL_RETRY_JITTER_SECONDS = _float_env("MODEL_RETRY_JITTER_SECONDS", default=0.5, minimum=0.0)


def _is_retryable_model_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code in RETRYABLE_STATUS_CODES:
        return True

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("Error") or {}
        error_code = str(error.get("Code", "")).lower()
        error_message = str(error.get("Message", body.get("message", ""))).lower()
        if any(token in error_code for token in RETRYABLE_ERROR_CODE_SUBSTRINGS):
            return True
        if any(token in error_message for token in RETRYABLE_MESSAGE_SUBSTRINGS):
            return True

    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        error_code = str(error.get("Code", "")).lower()
        error_message = str(error.get("Message", "")).lower()
        if any(token in error_code for token in RETRYABLE_ERROR_CODE_SUBSTRINGS):
            return True
        if any(token in error_message for token in RETRYABLE_MESSAGE_SUBSTRINGS):
            return True

    message = str(exc).lower()
    if any(token in message for token in RETRYABLE_ERROR_CODE_SUBSTRINGS):
        return True
    return any(token in message for token in RETRYABLE_MESSAGE_SUBSTRINGS)


def _compute_backoff_seconds(attempt: int) -> float:
    base_delay = MODEL_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
    jitter = random.uniform(0.0, MODEL_RETRY_JITTER_SECONDS)
    return min(base_delay + jitter, MODEL_RETRY_MAX_SECONDS)


def _process_with_retry(note_text: str, source_name: str, detection: DetectionParameters) -> AgentResponse:
    for attempt in range(1, MODEL_RETRY_MAX_ATTEMPTS + 1):
        try:
            return asyncio.run(
                process_document(note_text, source_name=source_name, detection=detection, language="en")
            )
        except Exception as exc:
            if attempt >= MODEL_RETRY_MAX_ATTEMPTS or not _is_retryable_model_error(exc):
                raise

            sleep_seconds = _compute_backoff_seconds(attempt)
            logger.warning(
                "Retryable model error for %s (attempt %d/%d): %s. Retrying in %.2fs",
                source_name,
                attempt,
                MODEL_RETRY_MAX_ATTEMPTS,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    raise RuntimeError("Retry loop exited unexpectedly")


def build_occurrence_entities(
    note_text: str,
    pii_entities: list[dict],
    source_name: str,
) -> list[dict[str, str]]:
    """
    Expand unique entities into occurrence-level entries in document order.

    Example: John (line 1), date (line 2), John (line 3) ->
    [John, date, John]
    """
    positions = find_pii_positions(note_text, pii_entities, source_name=source_name)
    positions.sort(key=lambda item: (item.get("start", 0), item.get("end", 0)))
    return [{"type": item.get("type", ""), "value": item.get("value", "")} for item in positions]


def _process_record(record: SQSRecord) -> None:
    try:
        message = record.json_body
        batch_id = message["batch_id"]
        s3_key = message["s3_key"]
        filename = s3_key.split("/")[-1]
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename

        resp = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        note_text = resp["Body"].read().decode("utf-8")

        detection = DetectionParameters()
        response: AgentResponse = _process_with_retry(note_text, source_name=s3_key, detection=detection)

        pii_dicts = [e.model_dump() for e in response.pii_entities]
        redacted_text = redact_text(note_text, pii_dicts, source_name=s3_key)
        occurrence_pii_dicts = build_occurrence_entities(note_text, pii_dicts, source_name=s3_key)

        redacted_key = f"{batch_id}/output/{stem}_redacted.txt"
        s3_client.put_object(Bucket=BUCKET_NAME, Key=redacted_key, Body=redacted_text.encode("utf-8"))

        detection_key = f"{batch_id}/output/{stem}_entities.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=detection_key,
            Body=json.dumps({
                "pii_entities": occurrence_pii_dicts,
                "summary": response.summary,
                "needs_review": response.needs_review,
            }).encode("utf-8"),
        )

        logger.info("Processed %s -> %s (%d entities)", s3_key, redacted_key, len(response.pii_entities))
    except Exception:
        logger.exception("Error processing SQS message %s", record.message_id)
        raise


@logger.inject_lambda_context(clear_state=True)
def handler(event, context):
    return process_partial_response(
        event=event,
        record_handler=_process_record,
        processor=processor,
        context=context,
    )
