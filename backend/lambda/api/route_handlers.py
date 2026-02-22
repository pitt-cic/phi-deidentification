import json
import logging
import os
from datetime import datetime, timezone

import boto3

from . import storage

logger = logging.getLogger("pii_deidentification.api")
lambda_client = boto3.client("lambda")
INGESTION_FUNCTION_NAME = os.environ["INGESTION_FUNCTION_NAME"]
MIN_SORT_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


def parse_sort_datetime(value: str) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        return MIN_SORT_DATETIME
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return MIN_SORT_DATETIME


def parse_approved(raw_approved: object) -> bool:
    if isinstance(raw_approved, bool):
        return raw_approved
    return str(raw_approved).strip().lower() in {"1", "true", "yes", "y"}


def approval_text_key(batch_id: str, note_id: str) -> str:
    return f"{batch_id}/approvals/{note_id}_approved.txt"


def prior_approval_text_key(batch_id: str, note_id: str) -> str:
    return f"{batch_id}/approvals/{note_id}.txt"


def legacy_approval_key(batch_id: str, note_id: str) -> str:
    return f"{batch_id}/approvals/{note_id}.json"


def list_approval_objects_for_signature(batch_id: str) -> list[dict]:
    objects: list[dict] = []
    for obj in storage.list_objects(f"{batch_id}/approvals/", suffix=".txt"):
        if storage.approved_note_id_from_key(obj.get("key", "")):
            objects.append(obj)
    return objects


def get_saved_redacted_text(batch_id: str, note_id: str) -> str | None:
    return storage.read_text(approval_text_key(batch_id, note_id))


def is_note_approved(batch_id: str, note_id: str) -> bool:
    return storage.read_text(approval_text_key(batch_id, note_id)) is not None


def resolve_redacted_text(
    batch_id: str,
    note_id: str,
    provided_redacted_text: object | None,
    existing_saved_text: str | None = None,
) -> str:
    if provided_redacted_text is not None:
        if not isinstance(provided_redacted_text, str):
            raise ValueError("Field 'redacted_text' must be a string when provided")
        return provided_redacted_text

    if existing_saved_text is not None:
        return existing_saved_text

    return storage.read_text(f"{batch_id}/output/{note_id}_redacted.txt") or ""


def update_batch_approval_metadata(
    *,
    batch_id: str,
    meta: dict,
    input_count: int,
    required_note_ids: set[str],
) -> tuple[int, bool]:
    output_count = len(storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt"))
    status = storage.compute_status(input_count, output_count, meta.get("status", "created"))
    meta["status"] = status

    approval_objects = list_approval_objects_for_signature(batch_id)
    approval_signature = storage.objects_signature(approval_objects)
    approved_note_ids = storage.list_approved_note_ids(batch_id)
    approval_stats = storage.compute_approval_stats(batch_id, approved_note_ids, required_note_ids)
    meta["approval_stats"] = approval_stats
    meta["approval_stats_signature"] = approval_signature

    approved_required_note_count = int(approval_stats.get("approved_required_note_count", 0))
    all_approved = (
        status == "completed"
        and len(required_note_ids) > 0
        and approved_required_note_count == len(required_note_ids)
    )
    meta["all_approved"] = all_approved
    storage.save_metadata(batch_id, meta)

    return approved_required_note_count, all_approved


def async_invoke_ingestion(batch_id: str) -> None:
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
    limit, offset = storage.parse_pagination(query)
    batch_ids = storage.list_batch_ids()
    no_metadata_batches = []
    metadata_batches = []
    for bid in batch_ids:
        meta = storage.read_json(f"{bid}/metadata.json") or {}
        created_at = str(meta.get("created_at", "")).strip()
        has_input = storage.prefix_has_non_folder_object(f"{bid}/input/")
        batch = {
            "batch_id": bid,
            "created_at": created_at,
            "status": meta.get("status", "created"),
            "all_approved": bool(meta.get("all_approved", False)),
            "has_input": has_input,
        }
        if created_at:
            batch["_created_sort_value"] = parse_sort_datetime(created_at)
            metadata_batches.append(batch)
        else:
            no_metadata_batches.append(batch)

    no_metadata_batches.sort(key=lambda b: b.get("batch_id", ""), reverse=True)
    metadata_batches.sort(
        key=lambda b: (b.get("_created_sort_value", MIN_SORT_DATETIME), b.get("batch_id", "")),
        reverse=True,
    )

    for batch in metadata_batches:
        batch.pop("_created_sort_value", None)

    all_batches = no_metadata_batches + metadata_batches
    return 200, storage.paginate(all_batches, limit, offset)


def get_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    input_keys = storage.list_keys(f"{batch_id}/input/")
    input_count = len(input_keys)
    required_note_ids = {storage.stem(key) for key in input_keys}
    batch_object_count = len(storage.list_keys(f"{batch_id}/"))
    output_count = len(storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt"))
    entity_objects = storage.list_objects(f"{batch_id}/output/", suffix="_entities.json")
    entity_keys = [obj["key"] for obj in entity_objects]
    entity_file_count = len(entity_keys)
    entity_signature = storage.objects_signature(entity_objects)
    if input_count == 0 and output_count == 0 and not meta.get("created_at") and batch_object_count == 0:
        return 404, {"error": f"Batch '{batch_id}' not found"}

    metadata_changed = False
    status = storage.compute_status(input_count, output_count, meta.get("status", "created"))
    if status != meta.get("status"):
        meta["status"] = status
        metadata_changed = True

    pii_stats = meta.get("pii_stats")
    if not isinstance(pii_stats, dict) or meta.get("pii_stats_signature") != entity_signature:
        pii_stats = storage.compute_pii_stats(batch_id, entity_keys)
        meta["pii_stats"] = pii_stats
        meta["pii_stats_entity_file_count"] = entity_file_count
        meta["pii_stats_signature"] = entity_signature
        metadata_changed = True

    approval_objects = list_approval_objects_for_signature(batch_id)
    approval_signature = storage.objects_signature(approval_objects)
    approved_note_ids = storage.list_approved_note_ids(batch_id)
    approval_stats = meta.get("approval_stats")
    if (
        not isinstance(approval_stats, dict)
        or meta.get("approval_stats_signature") != approval_signature
        or "approved_required_note_count" not in approval_stats
    ):
        approval_stats = storage.compute_approval_stats(batch_id, approved_note_ids, required_note_ids)
        meta["approval_stats"] = approval_stats
        meta["approval_stats_signature"] = approval_signature
        metadata_changed = True

    approved_required_note_count = int(approval_stats.get("approved_required_note_count", 0))
    all_approved = (
        status == "completed"
        and len(required_note_ids) > 0
        and approved_required_note_count == len(required_note_ids)
    )
    if bool(meta.get("all_approved", False)) != all_approved:
        meta["all_approved"] = all_approved
        metadata_changed = True

    if metadata_changed:
        storage.save_metadata(batch_id, meta)

    return 200, {
        **meta,
        "status": status,
        "input_count": input_count,
        "output_count": output_count,
        "pii_stats": pii_stats,
        "all_approved": all_approved,
    }


def start_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    input_count = len(storage.list_keys(f"{batch_id}/input/"))
    if input_count == 0:
        return 400, {"error": f"No input notes found in batch '{batch_id}'"}

    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    timestamp = datetime.now(timezone.utc).isoformat()
    meta["batch_id"] = batch_id
    if not meta.get("created_at"):
        meta["created_at"] = timestamp
    meta["status"] = "processing"
    meta["started_at"] = timestamp
    meta["all_approved"] = False
    storage.save_metadata(batch_id, meta)
    async_invoke_ingestion(batch_id)
    return 200, {"status": "started", "batch_id": batch_id}


def list_notes(params: dict, body: dict, query: dict) -> tuple[int, dict]:
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
        "summary": detection.get("summary", ""),
        "needs_review": detection.get("needs_review", False),
        "approved": is_note_approved(batch_id, note_id),
    }


def approve_note(params: dict, body: dict, query: dict) -> tuple[int, dict]:
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

    if approved:
        storage.put_text(approval_txt, redacted_text)
    else:
        storage.delete_key(approval_txt)
    storage.delete_key(prior_approval_txt)
    storage.delete_key(legacy_approval)

    approval = {
        "note_id": note_id,
        "approved": approved,
        "redacted_text": redacted_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    update_batch_approval_metadata(
        batch_id=batch_id,
        meta=meta,
        input_count=len(input_keys),
        required_note_ids=required_note_ids,
    )

    return 200, approval


def approve_all_notes(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    input_keys = storage.list_keys(f"{batch_id}/input/")
    input_count = len(input_keys)
    required_note_ids = sorted({storage.stem(key) for key in input_keys})
    if input_count == 0 and not meta.get("created_at"):
        return 404, {"error": f"Batch '{batch_id}' not found"}

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

    required_note_id_set = set(required_note_ids)
    approved_required_note_count, all_approved = update_batch_approval_metadata(
        batch_id=batch_id,
        meta=meta,
        input_count=input_count,
        required_note_ids=required_note_id_set,
    )

    return 200, {
        "batch_id": batch_id,
        "required_note_count": len(required_note_id_set),
        "approved_note_count": approved_required_note_count,
        "all_approved": all_approved,
    }
