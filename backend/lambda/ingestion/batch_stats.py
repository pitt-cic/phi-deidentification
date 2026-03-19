"""DynamoDB batch stats initialization module."""

import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

STATS_TABLE_NAME = os.environ.get("STATS_TABLE_NAME", "")

_dynamodb_resource = None
_stats_table = None


def _get_stats_table():
    """Lazy initialization of DynamoDB table resource."""
    global _dynamodb_resource, _stats_table
    if not STATS_TABLE_NAME:
        return None
    if _stats_table is None:
        _dynamodb_resource = boto3.resource("dynamodb")
        _stats_table = _dynamodb_resource.Table(STATS_TABLE_NAME)
    return _stats_table


def build_initial_stats_item(batch_id: str, input_count: int) -> dict:
    """Build a complete stats item with all attributes initialized."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        # Core attributes
        "batch_id": batch_id,
        "record_type": "BATCH",
        "gsi_pk": "BATCH",
        "input_count": input_count,
        "processed_count": 0,
        "total_entities": 0,
        "notes_with_pii": 0,
        "approved_count": 0,
        "status": "processing",
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        # PHI type counts - all initialized to 0
        "pii_person_name": 0,
        "pii_address": 0,
        "pii_date": 0,
        "pii_other": 0,
        "pii_phone_number": 0,
        "pii_certificate_or_license_number": 0,
        "pii_vehicle_identifier": 0,
        "pii_medical_record_number": 0,
        "pii_health_plan_beneficiary_number": 0,
        "pii_account_number": 0,
        "pii_email": 0,
        "pii_ssn": 0,
        "pii_fax_number": 0,
        "pii_device_identifier": 0,
        "pii_ip_address": 0,
        "pii_biometric_identifier": 0,
        "pii_unknown": 0,
    }


def initialize_batch_stats(batch_id: str, input_count: int) -> None:
    """Initialize or update batch stats in DynamoDB for processing."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    item = build_initial_stats_item(batch_id, input_count)

    try:
        stats_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(batch_id) AND attribute_not_exists(record_type)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Item exists (created by create_batch.sh) - update status to processing
        # Preserves created_at and existing counters (defense against double-start)
        now = datetime.now(timezone.utc).isoformat()
        stats_table.update_item(
            Key={"batch_id": batch_id, "record_type": "BATCH"},
            UpdateExpression="SET #status = :status, started_at = :now, updated_at = :now, input_count = :input_count",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "processing",
                ":now": now,
                ":input_count": input_count,
            },
        )


def write_note_metadata(batch_id: str, note_id: str) -> None:
    """Write initial note metadata record to DynamoDB."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    try:
        stats_table.put_item(
            Item={
                "batch_id": batch_id,
                "record_type": f"NOTE#{note_id}",
                "note_id": note_id,
                "has_output": False,
                "approved": False,
            },
            ConditionExpression="attribute_not_exists(batch_id) AND attribute_not_exists(record_type)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Note already exists, ignore
