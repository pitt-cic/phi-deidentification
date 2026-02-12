import json
import os
import uuid
from datetime import datetime, timezone

import boto3

import storage

lambda_client = boto3.client("lambda")
INGESTION_FUNCTION_NAME = os.environ["INGESTION_FUNCTION_NAME"]


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
        })
    all_batches.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return 200, storage.paginate(all_batches, limit, offset)


def create_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = body.get("batch_id") or f"batch-{uuid.uuid4().hex[:8]}"
    meta = {"batch_id": batch_id, "created_at": datetime.now(timezone.utc).isoformat(), "status": "created"}
    storage.save_metadata(batch_id, meta)
    return 201, meta


def get_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    input_count = len(storage.list_keys(f"{batch_id}/input/"))
    output_count = len(storage.list_keys(f"{batch_id}/output/", suffix="_redacted.txt"))
    if input_count == 0 and output_count == 0 and not meta.get("created_at"):
        return 404, {"error": f"Batch '{batch_id}' not found"}
    status = storage.compute_status(input_count, output_count, meta.get("status", "created"))
    if status != meta.get("status"):
        meta["status"] = status
        storage.save_metadata(batch_id, meta)
    return 200, {**meta, "status": status, "input_count": input_count, "output_count": output_count}


def start_batch(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    meta = storage.read_json(f"{batch_id}/metadata.json") or {"batch_id": batch_id}
    meta["status"] = "processing"
    meta["started_at"] = datetime.now(timezone.utc).isoformat()
    storage.save_metadata(batch_id, meta)
    lambda_client.invoke(
        FunctionName=INGESTION_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps({"batch_id": batch_id}).encode("utf-8"),
    )
    return 200, {"status": "started", "batch_id": batch_id}


def get_upload_url(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id = params["batch_id"]
    filename = body.get("filename")
    if not filename:
        return 400, {"error": "filename is required"}
    filename = os.path.basename(filename)
    if not filename:
        return 400, {"error": "Invalid filename"}
    key = f"{batch_id}/input/{filename}"
    return 200, {"upload_url": storage.presigned_put_url(key), "key": key}


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
    redacted = storage.read_text(f"{batch_id}/output/{note_id}_redacted.txt") or ""
    detection = storage.read_json(f"{batch_id}/output/{note_id}_entities.json") or {}
    approval = storage.read_json(f"{batch_id}/approvals/{note_id}.json")
    return 200, {
        "note_id": note_id,
        "original_text": original_text,
        "redacted_text": redacted,
        "pii_entities": detection.get("pii_entities", []),
        "summary": detection.get("summary", ""),
        "needs_review": detection.get("needs_review", False),
        "approved": (approval or {}).get("approved", False),
    }


def approve_note(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id, note_id = params["batch_id"], params["note_id"]
    approval = {
        "note_id": note_id,
        "approved": body.get("approved", True),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    storage.put_json(f"{batch_id}/approvals/{note_id}.json", approval)
    return 200, approval


def get_download_url(params: dict, body: dict, query: dict) -> tuple[int, dict]:
    batch_id, note_id = params["batch_id"], params["note_id"]
    key = f"{batch_id}/output/{note_id}_redacted.txt"
    return 200, {"download_url": storage.presigned_get_url(key), "key": key}


HANDLERS = {
    "list_batches": list_batches,
    "create_batch": create_batch,
    "get_batch": get_batch,
    "start_batch": start_batch,
    "get_upload_url": get_upload_url,
    "list_notes": list_notes,
    "get_note": get_note,
    "approve_note": approve_note,
    "get_download_url": get_download_url,
}
