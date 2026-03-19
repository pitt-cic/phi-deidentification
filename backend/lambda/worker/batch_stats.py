"""DynamoDB batch stats increment module for worker."""

import os
from datetime import datetime, timezone

import boto3

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


def pii_type_to_attribute(pii_type: str) -> str:
    """Convert PHI type to lowercase DynamoDB attribute name."""
    return f"pii_{pii_type.lower().replace(' ', '_')}"


def increment_batch_stats(batch_id: str, pii_entities: list[dict], logger=None) -> None:
    """Atomically increment batch stats in DynamoDB using ADD."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    entity_count = len(pii_entities)
    has_pii = 1 if entity_count > 0 else 0

    # Count entities by type
    type_counts: dict[str, int] = {}
    for entity in pii_entities:
        pii_type = str(entity.get("type", "UNKNOWN")).upper()
        attr_name = pii_type_to_attribute(pii_type)
        type_counts[attr_name] = type_counts.get(attr_name, 0) + 1

    # Build ADD expression - simple and atomic
    add_parts = [
        "processed_count :one",
        "total_entities :entities",
        "notes_with_pii :has_pii",
    ]
    expr_values = {
        ":one": 1,
        ":entities": entity_count,
        ":has_pii": has_pii,
        ":now": datetime.now(timezone.utc).isoformat(),
    }

    # Add each PHI type count
    for i, (attr_name, count) in enumerate(type_counts.items()):
        alias = f":t{i}"
        add_parts.append(f"{attr_name} {alias}")
        expr_values[alias] = count

    try:
        stats_table.update_item(
            Key={"batch_id": batch_id, "record_type": "BATCH"},
            UpdateExpression=f"ADD {', '.join(add_parts)} SET updated_at = :now",
            ExpressionAttributeValues=expr_values,
        )
    except Exception as exc:
        if logger:
            logger.warning("Failed to update batch stats for %s: %s", batch_id, exc)


def set_partially_completed_status(batch_id: str, logger=None) -> None:
    """Set status to partially-completed and failed_at timestamp on first failure."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    now = datetime.now(timezone.utc).isoformat()

    try:
        stats_table.update_item(
            Key={"batch_id": batch_id, "record_type": "BATCH"},
            UpdateExpression="""
                SET #status = :status,
                    updated_at = :now,
                    failed_at = if_not_exists(failed_at, :now)
            """,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "partially-completed",
                ":now": now,
            },
        )
    except Exception as exc:
        if logger:
            logger.warning("Failed to set partially_completed status for %s: %s", batch_id, exc)


def set_completed_at_if_done(batch_id: str, logger=None) -> None:
    """Set completed_at timestamp and status to completed if all notes are processed."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    now = datetime.now(timezone.utc).isoformat()

    try:
        # Conditional update: only set completed_at if processed_count >= input_count
        # and completed_at is not already set
        stats_table.update_item(
            Key={"batch_id": batch_id, "record_type": "BATCH"},
            UpdateExpression="SET completed_at = :now, updated_at = :now, #status = :status",
            ConditionExpression="processed_count >= input_count AND attribute_not_exists(completed_at)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":now": now, ":status": "completed"},
        )
    except Exception as exc:
        # Condition failed or other error - this is expected if not done yet
        if logger:
            logger.debug("set_completed_at_if_done condition not met for %s: %s", batch_id, exc)


def is_final_failure_attempt(receive_count: int, max_receive_count: int) -> bool:
    """
    Determine if this is the final SQS delivery attempt before DLQ.

    Returns True on the final attempt (when message will go to DLQ next).
    """
    return receive_count >= max_receive_count


def mark_note_processed(batch_id: str, note_id: str, logger=None) -> None:
    """Update note metadata to indicate processing is complete."""
    stats_table = _get_stats_table()
    if not stats_table:
        return

    try:
        stats_table.update_item(
            Key={"batch_id": batch_id, "record_type": f"NOTE#{note_id}"},
            UpdateExpression="SET has_output = :val",
            ExpressionAttributeValues={":val": True},
        )
    except Exception as exc:
        if logger:
            logger.warning("Failed to mark note %s as processed: %s", note_id, exc)
