"""Route handler functions for batch and note management operations."""
import json
import os
from datetime import datetime, timezone

import boto3

import storage
from batch_stats import get_batch_stats, increment_approval_count, set_processing_status_for_redrive, set_approved_at, list_all_batches
from api_logger import logger

lambda_client = boto3.client("lambda")
sqs_client = boto3.client("sqs")

INGESTION_FUNCTION_NAME = os.environ["INGESTION_FUNCTION_NAME"]
DLQ_URL = os.environ.get("DLQ_URL", "")
QUEUE_URL = os.environ.get("QUEUE_URL", "")
MIN_SORT_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


def parse_sort_datetime(value: str) -> datetime:
    """Parse ISO datetime string for sorting.

    Args:
        value: ISO format datetime string to parse.

    Returns:
        Parsed datetime object, or MIN_SORT_DATETIME if parsing fails.
    """
    normalized = str(value or "").strip()
    if not normalized:
        return MIN_SORT_DATETIME
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return MIN_SORT_DATETIME


def parse_approved(raw_approved: object) -> bool:
    """Parse approval flag from various input formats.

    Args:
        raw_approved: Value to parse (bool, string like "true"/"1"/"yes").

    Returns:
        True if the value represents approval, False otherwise.
    """
    if isinstance(raw_approved, bool):
        return raw_approved
    return str(raw_approved).strip().lower() in {"1", "true", "yes", "y"}


def approval_text_key(batch_id: str, note_id: str) -> str:
    """Build S3 key for approved note text file.

    Args:
        batch_id: Batch identifier.
        note_id: Note identifier.

    Returns:
        S3 key path for the approved text file.
    """
    return f"{batch_id}/approvals/{note_id}_approved.txt"


def prior_approval_text_key(batch_id: str, note_id: str) -> str:
    """Build S3 key for legacy approval text file.

    Args:
        batch_id: Batch identifier.
        note_id: Note identifier.

    Returns:
        S3 key path for the legacy text file.
    """
    return f"{batch_id}/approvals/{note_id}.txt"


def legacy_approval_key(batch_id: str, note_id: str) -> str:
    """Build S3 key for legacy JSON approval file.

    Args:
        batch_id: Batch identifier.
        note_id: Note identifier.

    Returns:
        S3 key path for the legacy JSON approval file.
    """
    return f"{batch_id}/approvals/{note_id}.json"


def list_approval_objects_for_signature(batch_id: str) -> list[dict]:
    """List approval objects for generating batch signature.

    Args:
        batch_id: Batch identifier.

    Returns:
        List of S3 object metadata dicts for approved notes.
    """
    objects: list[dict] = []
    for obj in storage.list_objects(f"{batch_id}/approvals/", suffix=".txt"):
        if storage.approved_note_id_from_key(obj.get("key", "")):
            objects.append(obj)
    return objects


def get_saved_redacted_text(batch_id: str, note_id: str) -> str | None:
    """Read saved approved redacted text from S3.

    Args:
        batch_id: Batch identifier.
        note_id: Note identifier.

    Returns:
        The saved redacted text, or None if not found.
    """
    return storage.read_text(approval_text_key(batch_id, note_id))


def is_note_approved(batch_id: str, note_id: str) -> bool:
    """Check if a note has been approved.

    Args:
        batch_id: Batch identifier.
        note_id: Note identifier.

    Returns:
        True if the note has an approval file in S3, False otherwise.
    """
    return storage.read_text(approval_text_key(batch_id, note_id)) is not None


def resolve_redacted_text(
    batch_id: str,
    note_id: str,
    provided_redacted_text: object | None,
    existing_saved_text: str | None = None,
) -> str:
    """Resolve redacted text from provided, saved, or output sources.

    Args:
        batch_id: Batch identifier.
        note_id: Note identifier.
        provided_redacted_text: Explicitly provided redacted text from request.
        existing_saved_text: Previously saved redacted text, if any.

    Returns:
        The resolved redacted text string.

    Raises:
        ValueError: If provided_redacted_text is not a string.
    """
    if provided_redacted_text is not None:
        if not isinstance(provided_redacted_text, str):
            raise ValueError("Field 'redacted_text' must be a string when provided")
        return provided_redacted_text

    if existing_saved_text is not None:
        return existing_saved_text

    return storage.read_text(f"{batch_id}/output/{note_id}_redacted.txt") or ""


def async_invoke_ingestion(batch_id: str) -> None:
    """Asynchronously invoke ingestion Lambda for a batch.

    Args:
        batch_id: Batch identifier to process.

    Raises:
        RuntimeError: If the Lambda invocation fails.
    """
    response = lambda_client.invoke(
        FunctionName=INGESTION_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps({"batch_id": batch_id}).encode("utf-8"),
    )

    status_code = int(response.get("StatusCode", 0))
    function_error = response.get("FunctionError")
    if status_code == 202 and not function_error:
        logger.info("Invoked ingestion lambda asynchronously for batch %s", batch_id)
        return

    logger.error(
        "Failed to async invoke ingestion lambda (status_code=%s function_error=%s batch_id=%s)",
        status_code,
        function_error,
        batch_id,
    )
    raise RuntimeError("Failed to start ingestion process")


def list_batches(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle GET /batches request.

    Args:
        params: URL path parameters (unused).
        body: Request body (unused).
        query: Query parameters (limit, cursor).

    Returns:
        Tuple of (status_code, response_body) with paginated batch list.
    """
    limit, _ = storage.parse_pagination(query)
    cursor = query.get("cursor")

    result = list_all_batches(limit, cursor)

    batches = [
        {
            "batch_id": item["batch_id"],
            "status": item.get("status", "created"),
            "created_at": item.get("created_at", ""),
            "all_approved": (
                item.get("status") == "completed"
                and int(item.get("approved_count", 0)) >= int(item.get("input_count", 0))
                and int(item.get("input_count", 0)) > 0
            ),
        }
        for item in result["items"]
    ]

    return 200, {
        "items": batches,
        "total": len(batches),
        "limit": limit,
        "offset": 0,
        "next_cursor": result["next_cursor"],
    }


def get_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle GET /batches/{batch_id} request.

    Args:
        params: URL path parameters (batch_id).
        body: Request body (unused).
        query: Query parameters (unused).

    Returns:
        Tuple of (status_code, response_body) with batch stats or 404 error.
    """
    batch_id = params["batch_id"]

    dynamo_stats = get_batch_stats(batch_id)
    if dynamo_stats:
        return 200, dynamo_stats

    return 404, {"error": f"Batch '{batch_id}' not found"}


def start_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle POST /batches/{batch_id}/start request.

    Args:
        params: URL path parameters (batch_id).
        body: Request body (unused).
        query: Query parameters (unused).

    Returns:
        Tuple of (status_code, response_body) with start confirmation or error.
    """
    batch_id = params["batch_id"]
    input_count = len(storage.list_keys(f"{batch_id}/input/"))
    if input_count == 0:
        return 400, {"error": f"No input notes found in batch '{batch_id}'"}

    async_invoke_ingestion(batch_id)
    return 200, {"status": "started", "batch_id": batch_id}


def list_notes(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle GET /batches/{batch_id}/notes request.

    Args:
        params: URL path parameters (batch_id).
        body: Request body (unused).
        query: Query parameters (limit, offset).

    Returns:
        Tuple of (status_code, response_body) with paginated note list.
    """
    batch_id = params["batch_id"]
    limit, offset = storage.parse_pagination(query)
    input_keys = storage.list_keys(f"{batch_id}/input/")
    output_stems = {storage.stem(k).removesuffix("_redacted") for k in storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt")}
    approved_stems = storage.list_approved_note_ids(batch_id)
    notes = [
        {
            "note_id": storage.stem(key),
            "filename": key.rsplit("/", 1)[-1],
            "has_output": storage.stem(key) in output_stems,
            "approved": storage.stem(key) in approved_stems,
        }
        for key in input_keys
    ]
    return 200, storage.paginate(notes, limit, offset)


def get_note(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle GET /batches/{batch_id}/notes/{note_id} request.

    Args:
        params: URL path parameters (batch_id, note_id).
        body: Request body (unused).
        query: Query parameters (unused).

    Returns:
        Tuple of (status_code, response_body) with note details or 404 error.
    """
    batch_id, note_id = params["batch_id"], params["note_id"]
    input_keys = storage.list_keys(f"{batch_id}/input/")
    original_text = ""
    for key in input_keys:
        if storage.stem(key) == note_id:
            original_text = storage.read_text(key) or ""
            break
    if not original_text:
        return 404, {"error": f"Note '{note_id}' not found in batch '{batch_id}'"}
    output_redacted_text = storage.read_text(f"{batch_id}/output/{note_id}_redacted.txt") or ""
    detection = storage.read_json(f"{batch_id}/output/{note_id}_entities.json") or {}
    saved_redacted_text = get_saved_redacted_text(batch_id, note_id)
    review_redacted_text = saved_redacted_text if saved_redacted_text is not None else output_redacted_text
    return 200, {
        "note_id": note_id,
        "original_text": original_text,
        "redacted_text": review_redacted_text,
        "output_redacted_text": output_redacted_text,
        "pii_entities": detection.get("pii_entities", []),
        "approved": is_note_approved(batch_id, note_id),
    }


def approve_note(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle POST /batches/{batch_id}/notes/{note_id}/approve request.

    Args:
        params: URL path parameters (batch_id, note_id).
        body: Request body (approved, redacted_text).
        query: Query parameters (unused).

    Returns:
        Tuple of (status_code, response_body) with approval result or error.
    """
    batch_id, note_id = params["batch_id"], params["note_id"]
    input_keys = storage.list_keys(f"{batch_id}/input/")
    required_note_ids = {storage.stem(key) for key in input_keys}
    if note_id not in required_note_ids:
        return 404, {"error": f"Note '{note_id}' not found in batch '{batch_id}'"}

    raw_approved = body.get("approved", True)
    approved = parse_approved(raw_approved)

    approval_txt = approval_text_key(batch_id, note_id)
    prior_approval_txt = prior_approval_text_key(batch_id, note_id)
    legacy_approval = legacy_approval_key(batch_id, note_id)
    existing_saved_text = get_saved_redacted_text(batch_id, note_id)

    try:
        redacted_text = resolve_redacted_text(
            batch_id=batch_id,
            note_id=note_id,
            provided_redacted_text=body.get("redacted_text"),
            existing_saved_text=existing_saved_text,
        )
    except ValueError as error:
        return 400, {"error": str(error)}

    was_previously_approved = existing_saved_text is not None

    if approved:
        storage.put_text(approval_txt, redacted_text)
    else:
        storage.delete_key(approval_txt)
    storage.delete_key(prior_approval_txt)
    storage.delete_key(legacy_approval)

    # Update approval count in DynamoDB
    if approved and not was_previously_approved:
        increment_approval_count(batch_id, 1)
    elif not approved and was_previously_approved:
        increment_approval_count(batch_id, -1)

    # Check if all approved and set timestamp
    stats = get_batch_stats(batch_id)
    if stats and stats.get("all_approved"):
        set_approved_at(batch_id)

    return 200, {
        "note_id": note_id,
        "approved": approved,
        "redacted_text": redacted_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def approve_all_notes(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle POST /batches/{batch_id}/approve-all request.

    Args:
        params: URL path parameters (batch_id).
        body: Request body (unused).
        query: Query parameters (unused).

    Returns:
        Tuple of (status_code, response_body) with bulk approval result or error.
    """
    batch_id = params["batch_id"]
    input_keys = storage.list_keys(f"{batch_id}/input/")
    input_count = len(input_keys)
    required_note_ids = sorted({storage.stem(key) for key in input_keys})

    if input_count == 0:
        return 404, {"error": f"Batch '{batch_id}' not found or has no input files"}

    # Get current approval count to calculate delta
    stats = get_batch_stats(batch_id)
    current_approved = int(stats.get("approval_stats", {}).get("approved_note_count", 0)) if stats else 0

    for note_id in required_note_ids:
        existing_saved_text = get_saved_redacted_text(batch_id, note_id)
        redacted_text = resolve_redacted_text(
            batch_id=batch_id,
            note_id=note_id,
            provided_redacted_text=None,
            existing_saved_text=existing_saved_text,
        )
        storage.put_text(approval_text_key(batch_id, note_id), redacted_text)
        storage.delete_key(prior_approval_text_key(batch_id, note_id))
        storage.delete_key(legacy_approval_key(batch_id, note_id))

    # Update approval count: set to total required notes
    new_approved = len(required_note_ids)
    delta = new_approved - current_approved
    if delta != 0:
        increment_approval_count(batch_id, delta)

    # Set approved_at timestamp
    set_approved_at(batch_id)

    return 200, {
        "batch_id": batch_id,
        "required_note_count": len(required_note_ids),
        "approved_note_count": new_approved,
        "all_approved": True,
    }


def redrive_dlq(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    """Handle POST /batches/{batch_id}/redrive request.

    Move failed messages for a batch from DLQ back to main queue.

    Args:
        params: URL path parameters (batch_id).
        body: Request body (unused).
        query: Query parameters (unused).

    Returns:
        Tuple of (status_code, response_body) with redrive result.
    """
    batch_id = params["batch_id"]

    if not DLQ_URL or not QUEUE_URL:
        return 500, {"error": "DLQ redrive not configured"}

    redriven_count = 0
    max_iterations = 100  # Safety limit

    for _ in range(max_iterations):
        # Receive up to 10 messages from DLQ
        response = sqs_client.receive_message(
            QueueUrl=DLQ_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1,
            VisibilityTimeout=30,
        )

        messages = response.get("Messages", [])
        if not messages:
            break

        for message in messages:
            try:
                msg_body = json.loads(message["Body"])
                if msg_body.get("batch_id") != batch_id:
                    continue  # Skip messages from other batches

                # Re-send to main queue
                sqs_client.send_message(
                    QueueUrl=QUEUE_URL,
                    MessageBody=message["Body"],
                )

                # Delete from DLQ
                sqs_client.delete_message(
                    QueueUrl=DLQ_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                )

                redriven_count += 1
            except Exception as exc:
                logger.warning("Failed to redrive message: %s", exc)

    # Update batch status
    if redriven_count > 0:
        set_processing_status_for_redrive(batch_id)
        return 200, {
            "batch_id": batch_id,
            "redriven_count": redriven_count,
            "status": "processing",
        }

    # Edge case: DLQ empty but status stuck - check if all notes processed
    stats = get_batch_stats(batch_id)
    if stats and stats.get("output_count", 0) >= stats.get("input_count", 0):
        # All notes processed, DLQ empty - fix stale status
        from batch_stats import _get_stats_table
        from datetime import datetime, timezone
        stats_table = _get_stats_table()
        if stats_table:
            now = datetime.now(timezone.utc).isoformat()
            stats_table.update_item(
                Key={"batch_id": batch_id},
                UpdateExpression="SET #status = :status, completed_at = if_not_exists(completed_at, :now), updated_at = :now",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "completed", ":now": now},
            )
        return 200, {
            "batch_id": batch_id,
            "redriven_count": 0,
            "status": "completed",
        }

    return 200, {
        "batch_id": batch_id,
        "redriven_count": 0,
        "status": "partially-completed",
    }
