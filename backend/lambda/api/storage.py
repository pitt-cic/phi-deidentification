"""S3 storage operations for notes, redactions, and approvals."""
import json
import os

import boto3

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

DEFAULT_PAGE_SIZE = 50
APPROVED_SUFFIX = "_approved.txt"


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


def prefix_has_non_folder_object(prefix: str) -> bool:
    try:
        resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, MaxKeys=2)
    except Exception:
        return False

    for obj in resp.get("Contents", []):
        if obj.get("Key") != prefix:
            return True
    return False


def stem(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def approved_note_id_from_key(key: str) -> str | None:
    name = key.rsplit("/", 1)[-1]
    if not name.endswith(APPROVED_SUFFIX):
        return None
    note_id = name[: -len(APPROVED_SUFFIX)]
    return note_id or None


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


def put_text(key: str, data: str) -> None:
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=data.encode("utf-8"),
    )


def delete_key(key: str) -> None:
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=key)
    except Exception:
        return


def list_approved_note_ids(batch_id: str) -> set[str]:
    approved_note_ids: set[str] = set()
    approval_keys = list_keys(f"{batch_id}/approvals/", suffix=".txt")
    for key in approval_keys:
        note_id = approved_note_id_from_key(key)
        if note_id:
            approved_note_ids.add(note_id)

    return approved_note_ids
