"""S3 storage operations for notes, redactions, and approvals."""
import json
import os

import boto3

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

DEFAULT_PAGE_SIZE = 50


def _decode_text(data: bytes) -> str:
    """Decode bytes to string, auto-detecting UTF-16 BOM."""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    return data.decode("utf-8")


APPROVED_SUFFIX = "_approved.txt"


def list_keys(prefix: str, suffix: str = "") -> list[str]:
    """List all S3 object keys under a prefix.

    Args:
        prefix: S3 key prefix to search under.
        suffix: Optional suffix filter for keys.

    Returns:
        List of S3 keys matching the prefix and suffix.
    """
    return [obj["key"] for obj in list_objects(prefix, suffix)]


def list_objects(prefix: str, suffix: str = "") -> list[dict]:
    """List S3 objects with metadata under a prefix.

    Args:
        prefix: S3 key prefix to search under.
        suffix: Optional suffix filter for keys.

    Returns:
        List of dicts with key, etag, size, and last_modified for each object.
    """
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
    """List all batch IDs from S3 bucket top-level prefixes.

    Returns:
        List of batch ID strings (excluding hidden prefixes starting with '.').
    """
    out = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            bid = cp["Prefix"].rstrip("/")
            if not bid.startswith("."):
                out.append(bid)
    return out


def read_json(key: str) -> dict | None:
    """Read and parse a JSON file from S3.

    Args:
        key: S3 object key.

    Returns:
        Parsed JSON as dict, or None if read fails.
    """
    try:
        resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return None


def read_text(key: str) -> str | None:
    """Read a text file from S3.

    Args:
        key: S3 object key.

    Returns:
        File contents as string, or None if read fails.
    """
    try:
        resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return _decode_text(resp["Body"].read())
    except Exception:
        return None


def prefix_has_non_folder_object(prefix: str) -> bool:
    """Check if an S3 prefix contains any non-folder objects.

    Args:
        prefix: S3 key prefix to check.

    Returns:
        True if objects exist under the prefix (excluding the prefix itself).
    """
    try:
        resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, MaxKeys=2)
    except Exception:
        return False

    for obj in resp.get("Contents", []):
        if obj.get("Key") != prefix:
            return True
    return False


def stem(key: str) -> str:
    """Extract filename stem (name without extension) from an S3 key.

    Args:
        key: S3 object key.

    Returns:
        Filename without extension.
    """
    name = key.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def approved_note_id_from_key(key: str) -> str | None:
    """Extract note ID from an approval file key.

    Args:
        key: S3 key for an approval file (e.g., 'batch/approvals/note123_approved.txt').

    Returns:
        Note ID string, or None if key doesn't match approval format.
    """
    name = key.rsplit("/", 1)[-1]
    if not name.endswith(APPROVED_SUFFIX):
        return None
    note_id = name[: -len(APPROVED_SUFFIX)]
    return note_id or None


def parse_pagination(query: dict) -> tuple[int, int]:
    """Parse pagination parameters from query string.

    Args:
        query: Query string dict with optional 'limit' and 'offset' keys.

    Returns:
        Tuple of (limit, offset) with validated bounds (1-200 for limit).
    """
    try:
        limit = max(1, min(int(query.get("limit", DEFAULT_PAGE_SIZE)), 200))
        offset = max(int(query.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit = DEFAULT_PAGE_SIZE
        offset = 0
    return limit, offset


def paginate(items: list, limit: int, offset: int) -> dict:
    """Apply pagination to a list of items.

    Args:
        items: Full list of items to paginate.
        limit: Maximum number of items to return.
        offset: Starting index in the list.

    Returns:
        Dict with 'items', 'total', 'limit', and 'offset' keys.
    """
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


def put_json(key: str, data: dict) -> None:
    """Write a JSON object to S3.

    Args:
        key: S3 object key.
        data: Dict to serialize and store.
    """
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data).encode("utf-8"),
    )


def put_text(key: str, data: str) -> None:
    """Write text content to S3.

    Args:
        key: S3 object key.
        data: Text content to store.
    """
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=data.encode("utf-8"),
    )


def delete_key(key: str) -> None:
    """Delete an object from S3.

    Args:
        key: S3 object key to delete.
    """
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=key)
    except Exception:
        return


def list_approved_note_ids(batch_id: str) -> set[str]:
    """Get all approved note IDs for a batch.

    Args:
        batch_id: Batch identifier.

    Returns:
        Set of note ID strings that have been approved.
    """
    approved_note_ids: set[str] = set()
    approval_keys = list_keys(f"{batch_id}/approvals/", suffix=".txt")
    for key in approval_keys:
        note_id = approved_note_id_from_key(key)
        if note_id:
            approved_note_ids.add(note_id)

    return approved_note_ids
