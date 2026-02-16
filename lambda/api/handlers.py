import json
import os
from datetime import datetime, timezone

import boto3

import storage

lambda_client = boto3.client("lambda")
INGESTION_FUNCTION_NAME = os.environ["INGESTION_FUNCTION_NAME"]


def parse_approved(raw_approved: object) -> bool:
    if isinstance(raw_approved, bool):
        return raw_approved
    return str(raw_approved).strip().lower() in {"1", "true", "yes", "y"}


def get_saved_redacted_text(approval: dict | None) -> str | None:
    if isinstance(approval, dict) and isinstance(approval.get("redacted_text"), str):
        return approval["redacted_text"]
    return None


def resolve_redacted_text(
    batch_id: str,
    note_id: str,
    provided_redacted_text: object | None,
    existing_approval: dict | None = None,
) -> str:
    if provided_redacted_text is not None:
        if not isinstance(provided_redacted_text, str):
            raise ValueError("Field 'redacted_text' must be a string when provided")
        return provided_redacted_text

    saved_text = get_saved_redacted_text(existing_approval)
    if saved_text is not None:
        return saved_text

    return storage.read_text(f"{batch_id}/output/{note_id}_redacted.txt") or ""


def list_batches(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    limit, offset = storage.parse_pagination(query)
    batch_ids = storage.list_batch_ids()
    all_batches = []
    for bid in batch_ids:
        meta = storage.read_json(f"{bid}/metadata.json") or {}
        all_batches.append({
            "batch_id": bid,
            "created_at": meta.get("created_at", ""),
            "status": meta.get("status", "unknown"),
            "all_approved": bool(meta.get("all_approved", False)),
        })
    all_batches.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return 200, storage.paginate(all_batches, limit, offset)


def get_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    input_keys = storage.list_keys(f"{batch_id}/input/")
    input_count = len(input_keys)
    required_note_ids = {storage.stem(key) for key in input_keys}
    output_count = len(storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt"))
    entity_objects = storage.list_objects(f"{batch_id}/output/", suffix="_entities.json")
    entity_keys = [obj["key"] for obj in entity_objects]
    entity_file_count = len(entity_keys)
    entity_signature = storage.objects_signature(entity_objects)
    if input_count == 0 and output_count == 0 and not meta.get("created_at"):
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

    approval_objects = storage.list_objects(f"{batch_id}/approvals/", suffix=".json")
    approval_keys = [obj["key"] for obj in approval_objects]
    approval_signature = storage.objects_signature(approval_objects)
    approval_stats = meta.get("approval_stats")
    if (
        not isinstance(approval_stats, dict)
        or meta.get("approval_stats_signature") != approval_signature
        or "approved_required_note_count" not in approval_stats
    ):
        approval_stats = storage.compute_approval_stats(batch_id, approval_keys, required_note_ids)
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
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    meta["status"] = "processing"
    meta["started_at"] = datetime.now(timezone.utc).isoformat()
    meta["all_approved"] = False
    storage.save_metadata(batch_id, meta)
    lambda_client.invoke(
        FunctionName=INGESTION_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps({"batch_id": batch_id}).encode("utf-8"),
    )
    return 200, {"status": "started", "batch_id": batch_id}


def list_notes(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    limit, offset = storage.parse_pagination(query)
    input_keys = storage.list_keys(f"{batch_id}/input/")
    output_stems = {storage.stem(k).removesuffix("_redacted") for k in storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt")}
    approved_stems = set()
    for key in storage.list_keys(f"{batch_id}/approvals/"):
        data = storage.read_json(key)
        if data and data.get("approved"):
            approved_stems.add(storage.stem(key))
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
    approval = storage.read_json(f"{batch_id}/approvals/{note_id}.json")
    saved_redacted_text = get_saved_redacted_text(approval)
    review_redacted_text = saved_redacted_text if saved_redacted_text is not None else output_redacted_text
    return 200, {
        "note_id": note_id,
        "original_text": original_text,
        "redacted_text": review_redacted_text,
        "output_redacted_text": output_redacted_text,
        "pii_entities": detection.get("pii_entities", []),
        "summary": detection.get("summary", ""),
        "needs_review": detection.get("needs_review", False),
        "approved": (approval or {}).get("approved", False),
    }


def approve_note(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id, note_id = params["batch_id"], params["note_id"]
    input_keys = storage.list_keys(f"{batch_id}/input/")
    required_note_ids = {storage.stem(key) for key in input_keys}
    if note_id not in required_note_ids:
        return 404, {"error": f"Note '{note_id}' not found in batch '{batch_id}'"}

    raw_approved = body.get("approved", True)
    approved = parse_approved(raw_approved)

    approval_key = f"{batch_id}/approvals/{note_id}.json"
    existing_approval = storage.read_json(approval_key) or {}

    try:
        redacted_text = resolve_redacted_text(
            batch_id=batch_id,
            note_id=note_id,
            provided_redacted_text=body.get("redacted_text"),
            existing_approval=existing_approval,
        )
    except ValueError as error:
        return 400, {"error": str(error)}

    approval = {
        "note_id": note_id,
        "approved": approved,
        "redacted_text": redacted_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    storage.put_json(approval_key, approval)

    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    input_count = len(input_keys)
    output_count = len(storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt"))
    status = storage.compute_status(input_count, output_count, meta.get("status", "created"))
    meta["status"] = status

    approval_objects = storage.list_objects(f"{batch_id}/approvals/", suffix=".json")
    approval_keys = [obj["key"] for obj in approval_objects]
    approval_signature = storage.objects_signature(approval_objects)
    approval_stats = storage.compute_approval_stats(batch_id, approval_keys, required_note_ids)
    meta["approval_stats"] = approval_stats
    meta["approval_stats_signature"] = approval_signature

    approved_required_note_count = int(approval_stats.get("approved_required_note_count", 0))
    meta["all_approved"] = (
        status == "completed"
        and len(required_note_ids) > 0
        and approved_required_note_count == len(required_note_ids)
    )
    storage.save_metadata(batch_id, meta)

    return 200, approval


def approve_all_notes(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    input_keys = storage.list_keys(f"{batch_id}/input/")
    input_count = len(input_keys)
    required_note_ids = sorted({storage.stem(key) for key in input_keys})
    if input_count == 0 and not meta.get("created_at"):
        return 404, {"error": f"Batch '{batch_id}' not found"}

    timestamp = datetime.now(timezone.utc).isoformat()
    for note_id in required_note_ids:
        approval_key = f"{batch_id}/approvals/{note_id}.json"
        existing_approval = storage.read_json(approval_key) or {}
        redacted_text = resolve_redacted_text(
            batch_id=batch_id,
            note_id=note_id,
            provided_redacted_text=None,
            existing_approval=existing_approval,
        )
        storage.put_json(
            approval_key,
            {
                "note_id": note_id,
                "approved": True,
                "redacted_text": redacted_text,
                "timestamp": timestamp,
            },
        )

    output_count = len(storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt"))
    status = storage.compute_status(input_count, output_count, meta.get("status", "created"))
    meta["status"] = status

    required_note_id_set = set(required_note_ids)
    approval_objects = storage.list_objects(f"{batch_id}/approvals/", suffix=".json")
    approval_keys = [obj["key"] for obj in approval_objects]
    approval_signature = storage.objects_signature(approval_objects)
    approval_stats = storage.compute_approval_stats(batch_id, approval_keys, required_note_id_set)
    meta["approval_stats"] = approval_stats
    meta["approval_stats_signature"] = approval_signature

    approved_required_note_count = int(approval_stats.get("approved_required_note_count", 0))
    all_approved = (
        status == "completed"
        and len(required_note_id_set) > 0
        and approved_required_note_count == len(required_note_id_set)
    )
    meta["all_approved"] = all_approved
    storage.save_metadata(batch_id, meta)

    return 200, {
        "batch_id": batch_id,
        "required_note_count": len(required_note_id_set),
        "approved_note_count": approved_required_note_count,
        "all_approved": all_approved,
    }


HANDLERS = {
    "list_batches": list_batches,
    "get_batch": get_batch,
    "start_batch": start_batch,
    "list_notes": list_notes,
    "get_note": get_note,
    "approve_note": approve_note,
    "approve_all_notes": approve_all_notes,
}
