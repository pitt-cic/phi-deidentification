"""
Ingestion Lambda.

Invoke via CLI:
  aws lambda invoke \
    --function-name <IngestionLambdaName> \
    --payload '{"batch_id": "batch-001"}' \
    response.json

Reads all files under s3://<bucket>/<batch_id>/input/
and enqueues each as an SQS message with the S3 reference.
"""

import os
import json
import boto3
import time
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

from batch_stats import initialize_batch_stats, write_note_metadata

s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")

BUCKET_NAME = os.environ["BUCKET_NAME"]
QUEUE_URL = os.environ["QUEUE_URL"]

metrics = Metrics(namespace="PIIDeidentification", service="ingestion")
logger = Logger(service="phi_deidentification.ingestion")


def extract_note_id(s3_key: str) -> str:
    """Extract note ID from S3 key (filename without extension)."""
    filename = s3_key.rsplit("/", 1)[-1]
    return filename.rsplit(".", 1)[0] if "." in filename else filename


@metrics.log_metrics
@logger.inject_lambda_context(clear_state=True)
def handler(event, context):
    """Lambda entry point for batch ingestion.

    Lists all files under {batch_id}/input/ in S3 and enqueues
    each as an SQS message for worker processing.

    Args:
        event: Lambda event dict with 'batch_id' key.
        context: Lambda context object (unused).

    Returns:
        Dict with status, batch_id, file_count, and failed_count.
    """
    start = time.perf_counter()
    batch_id = event["batch_id"]
    prefix = f"{batch_id}/input/"

    # List all objects under the input prefix
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # skip the "folder" marker itself
            if key == prefix:
                continue
            keys.append(key)

    if not keys:
        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.add_metric(name="IngestionEnqueueTime", unit=MetricUnit.Milliseconds, value=elapsed_ms)
        metrics.add_metric(name="IngestionFileCount", unit=MetricUnit.Count, value=0)
        return {"status": "no_files", "batch_id": batch_id}

    # Initialize stats record in DynamoDB
    initialize_batch_stats(batch_id, len(keys))

    # Write note metadata for each note
    for key in keys:
        note_id = extract_note_id(key)
        write_note_metadata(batch_id, note_id)

    # Enqueue files using SQS batch send (up to 10 per call)
    failed = 0
    for i in range(0, len(keys), 10):
        batch = keys[i : i + 10]
        entries = [
            {
                "Id": str(idx),
                "MessageBody": json.dumps({
                    "batch_id": batch_id,
                    "s3_key": key,
                }),
            }
            for idx, key in enumerate(batch)
        ]
        resp = sqs_client.send_message_batch(
            QueueUrl=QUEUE_URL,
            Entries=entries,
        )
        failed += len(resp.get("Failed", []))

    elapsed_ms = (time.perf_counter() - start) * 1000
    metrics.add_metric(name="IngestionEnqueueTime", unit=MetricUnit.Milliseconds, value=elapsed_ms)
    metrics.add_metric(name="IngestionFileCount", unit=MetricUnit.Count, value=len(keys))

    return {
        "status": "enqueued",
        "batch_id": batch_id,
        "file_count": len(keys),
        "failed_count": failed,
    }
