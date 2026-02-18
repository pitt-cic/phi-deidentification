import asyncio
import json
import os

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
        response: AgentResponse = asyncio.run(
            process_document(note_text, source_name=s3_key, detection=detection, language="en")
        )

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
