"""
Worker Lambda — SQS-triggered.

For each message:
1. Read medical note from S3 (s3_key from message)
2. Call process_document() to identify PII via Bedrock
3. Redact PII using redact_text()
4. Write redacted note to s3://<bucket>/<batch_id>/output/
"""

import asyncio
import json
import logging
import os

import boto3

from agent import AgentResponse, DetectionParameters
from main import process_document
from redact_pii import redact_text

logger = logging.getLogger("pii_deidentification.worker")
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

BUCKET_NAME = os.environ["BUCKET_NAME"]


def handler(event, context):
    batch_item_failures = []

    for record in event["Records"]:
        try:
            message = json.loads(record["body"])
            batch_id = message["batch_id"]
            s3_key = message["s3_key"]
            filename = s3_key.split("/")[-1]
            stem = filename.rsplit(".", 1)[0] if "." in filename else filename

            # 1. Read note from S3
            resp = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
            note_text = resp["Body"].read().decode("utf-8")

            # 2. Call Bedrock to identify PII
            detection = DetectionParameters()  # uses HIPAA 18 defaults
            response: AgentResponse = asyncio.run(
                process_document(
                    note_text,
                    source_name=s3_key,
                    detection=detection,
                    language="en",
                )
            )

            # 3. Redact PII from the note using the response
            pii_dicts = [e.model_dump() for e in response.pii_entities]
            redacted_text = redact_text(note_text, pii_dicts, source_name=s3_key)

            # 4. Write only the redacted note to S3
            redacted_key = f"{batch_id}/output/{stem}_redacted.txt"
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=redacted_key,
                Body=redacted_text.encode("utf-8"),
            )

            logger.info(
                "Processed %s -> %s (%d entities)",
                s3_key,
                redacted_key,
                len(response.pii_entities),
            )

        except Exception as e:
            logger.error("Error processing %s: %s", record["messageId"], e, exc_info=True)
            batch_item_failures.append(
                {"itemIdentifier": record["messageId"]}
            )

    return {"batchItemFailures": batch_item_failures}
