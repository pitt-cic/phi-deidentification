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
        # PII type counts - all initialized to 0
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
    """Initialize or reset batch stats in DynamoDB."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    item = build_initial_stats_item(batch_id, input_count)

    try:
        stats_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(batch_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Item exists - delete and recreate to fully reset all attributes
        stats_table.delete_item(Key={"batch_id": batch_id})
        stats_table.put_item(Item=item)
