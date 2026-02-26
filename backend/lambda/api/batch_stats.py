"""DynamoDB batch stats read module for API."""

import os
from datetime import datetime, timezone

import boto3

STATS_TABLE_NAME = os.environ.get("STATS_TABLE_NAME", "")
PII_ATTR_PREFIX = "pii_"

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


def get_batch_stats(batch_id: str) -> dict | None:
    """
    Read batch stats from DynamoDB.

    Returns None if DynamoDB is not configured or item not found.
    """
    stats_table = _get_stats_table()
    if not stats_table:
        return None

    response = stats_table.get_item(Key={"batch_id": batch_id})
    stats = response.get("Item")

    if not stats:
        return None

    input_count = int(stats.get("input_count", 0))
    processed_count = int(stats.get("processed_count", 0))
    failed_count = int(stats.get("failed_count", 0))
    approved_count = int(stats.get("approved_count", 0))

    # Compute derived status
    total_handled = processed_count + failed_count
    if total_handled >= input_count and input_count > 0:
        if failed_count > 0:
            status = "partially-completed"
        else:
            status = "completed"
    elif processed_count > 0 or failed_count > 0:
        status = "processing"
    else:
        status = stats.get("status", "created")

    all_approved = (
        status == "completed"
        and approved_count >= input_count
        and input_count > 0
    )

    # Extract pii_* attributes and convert to by_type dict
    # Filter out zero counts to match existing API response format
    pii_by_type = {}
    for key, value in stats.items():
        if key.startswith(PII_ATTR_PREFIX):
            count = int(value)
            if count > 0:
                pii_type = key[len(PII_ATTR_PREFIX):].upper()
                pii_by_type[pii_type] = count

    # Sort by count descending, then alphabetically
    sorted_pii_by_type = dict(sorted(
        pii_by_type.items(),
        key=lambda x: (-x[1], x[0])
    ))

    return {
        "batch_id": batch_id,
        "status": status,
        "input_count": input_count,
        "output_count": processed_count,
        "failed_count": failed_count,
        "all_approved": all_approved,
        "created_at": stats.get("created_at", ""),
        "started_at": stats.get("started_at", ""),
        "completed_at": stats.get("completed_at", ""),
        "failed_at": stats.get("failed_at", ""),
        "last_redrive_at": stats.get("last_redrive_at", ""),
        "approved_at": stats.get("approved_at", ""),
        "pii_stats": {
            "entity_file_count": processed_count,
            "notes_with_pii": int(stats.get("notes_with_pii", 0)),
            "total_entities": int(stats.get("total_entities", 0)),
            "by_type": sorted_pii_by_type,
        },
        "approval_stats": {
            "approved_note_count": approved_count,
            "approval_file_count": approved_count,
        },
    }


def increment_approval_count(batch_id: str, delta: int) -> None:
    """
    Atomically increment or decrement approval count.

    Args:
        batch_id: The batch ID
        delta: 1 for increment, -1 for decrement
    """
    stats_table = _get_stats_table()
    if not stats_table:
        return

    now = datetime.now(timezone.utc).isoformat()
    stats_table.update_item(
        Key={"batch_id": batch_id},
        UpdateExpression="ADD approved_count :delta SET updated_at = :now",
        ExpressionAttributeValues={":delta": delta, ":now": now},
    )


def reset_failed_count_and_set_redrive_timestamp(batch_id: str) -> None:
    """Reset failed_count to 0 and set last_redrive_at timestamp for redrive."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    now = datetime.now(timezone.utc).isoformat()
    stats_table.update_item(
        Key={"batch_id": batch_id},
        UpdateExpression="""
            SET failed_count = :zero,
                last_redrive_at = :now,
                status = :status,
                updated_at = :now
        """,
        ExpressionAttributeValues={
            ":zero": 0,
            ":now": now,
            ":status": "processing",
        },
    )


def set_approved_at(batch_id: str) -> None:
    """Set approved_at timestamp when all notes are approved."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    now = datetime.now(timezone.utc).isoformat()
    stats_table.update_item(
        Key={"batch_id": batch_id},
        UpdateExpression="SET approved_at = :now, updated_at = :now",
        ExpressionAttributeValues={":now": now},
    )
