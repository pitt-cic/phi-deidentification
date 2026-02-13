import asyncio
import json
import logging
import os

import boto3

from agent import AgentResponse, DetectionParameters
from main import process_document
from redact_pii import find_pii_positions, redact_text

logger = logging.getLogger("pii_deidentification.worker")
logger.setLevel(logging.INFO)

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


def handler(event, context):
    batch_item_failures = []

    for record in event["Records"]:
        try:
            message = json.loads(record["body"])
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

        except Exception as e:
            logger.error("Error processing %s: %s", record["messageId"], e, exc_info=True)
            batch_item_failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": batch_item_failures}
