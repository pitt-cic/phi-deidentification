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

s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")

BUCKET_NAME = os.environ["BUCKET_NAME"]
QUEUE_URL = os.environ["QUEUE_URL"]


def handler(event, context):
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
        return {"status": "no_files", "batch_id": batch_id}

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

    return {
        "status": "enqueued",
        "batch_id": batch_id,
        "file_count": len(keys),
        "failed_count": failed,
    }
