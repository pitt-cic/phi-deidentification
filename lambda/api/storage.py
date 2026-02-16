import json
import os
import hashlib

import boto3

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

DEFAULT_PAGE_SIZE = 50


def list_keys(prefix: str, suffix: str = "") -> list[str]:
    return [obj["key"] for obj in list_objects(prefix, suffix)]


def list_objects(prefix: str, suffix: str = "") -> list[dict]:
    objects: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key == prefix or (suffix and not key.endswith(suffix)):
                continue
            objects.append(
                {
                    "key": key,
                    "etag": str(obj.get("ETag", "")).strip('"'),
                    "size": int(obj.get("Size", 0)),
                    "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else "",
                }
            )
    return objects


def list_batch_ids() -> list[str]:
    out = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            bid = cp["Prefix"].rstrip("/")
            if not bid.startswith("."):
                out.append(bid)
    return out


def read_json(key: str) -> dict | None:
    try:
        resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return None


def read_text(key: str) -> str | None:
    try:
        resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return resp["Body"].read().decode("utf-8")
    except Exception:
        return None


def stem(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def compute_status(input_count: int, output_count: int, fallback: str = "created") -> str:
    if input_count == 0:
        return fallback
    if output_count >= input_count:
        return "completed"
    if output_count > 0:
        return "processing"
    return fallback


def save_metadata(batch_id: str, metadata: dict) -> None:
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=f"{batch_id}/metadata.json",
        Body=json.dumps(metadata).encode("utf-8"),
    )


def parse_pagination(query: dict) -> tuple[int, int]:
    try:
        limit = max(1, min(int(query.get("limit", DEFAULT_PAGE_SIZE)), 200))
        offset = max(int(query.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit = DEFAULT_PAGE_SIZE
        offset = 0
    return limit, offset


def paginate(items: list, limit: int, offset: int) -> dict:
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


def put_json(key: str, data: dict) -> None:
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data).encode("utf-8"),
    )


def objects_signature(objects: list[dict]) -> str:
    hasher = hashlib.sha256()
    for obj in sorted(objects, key=lambda item: item.get("key", "")):
        hasher.update(str(obj.get("key", "")).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(obj.get("etag", "")).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(obj.get("size", 0)).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(obj.get("last_modified", "")).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def compute_pii_stats(batch_id: str, entity_keys: list[str] | None = None) -> dict:
    if entity_keys is None:
        entity_keys = list_keys(f"{batch_id}/output/", suffix="_entities.json")

    total_entities = 0
    notes_with_pii = 0
    by_type: dict[str, int] = {}

    for key in entity_keys:
        detection = read_json(key) or {}
        entities = detection.get("pii_entities", [])
        if not isinstance(entities, list):
            continue

        note_entity_count = 0
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            raw_type = str(entity.get("type", "")).strip()
            normalized_type = raw_type.upper() if raw_type else "UNKNOWN"
            by_type[normalized_type] = by_type.get(normalized_type, 0) + 1
            total_entities += 1
            note_entity_count += 1

        if note_entity_count > 0:
            notes_with_pii += 1

    sorted_by_type = {
        entity_type: count
        for entity_type, count in sorted(by_type.items(), key=lambda item: (-item[1], item[0]))
    }

    return {
        "entity_file_count": len(entity_keys),
        "notes_with_pii": notes_with_pii,
        "total_entities": total_entities,
        "by_type": sorted_by_type,
    }


def compute_approval_stats(
    batch_id: str,
    approval_keys: list[str] | None = None,
    required_note_ids: set[str] | None = None,
) -> dict:
    if approval_keys is None:
        approval_keys = list_keys(f"{batch_id}/approvals/", suffix=".json")

    approved_note_count = 0
    approved_required_note_count = 0
    for key in approval_keys:
        data = read_json(key) or {}
        if data.get("approved") is True:
            approved_note_count += 1
            if required_note_ids is None or stem(key) in required_note_ids:
                approved_required_note_count += 1

    stats = {
        "approval_file_count": len(approval_keys),
        "approved_note_count": approved_note_count,
    }
    if required_note_ids is not None:
        stats["approved_required_note_count"] = approved_required_note_count
    return stats
