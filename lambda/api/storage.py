import json
import os

import boto3

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

DEFAULT_PAGE_SIZE = 50


def list_keys(prefix: str, suffix: str = "") -> list[str]:
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key == prefix or (suffix and not key.endswith(suffix)):
                continue
            keys.append(key)
    return keys


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
        limit = min(int(query.get("limit", DEFAULT_PAGE_SIZE)), 200)
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


def presigned_put_url(key: str, content_type: str = "text/plain", expires: int = 3600) -> str:
    return s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET_NAME, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presigned_get_url(key: str, expires: int = 3600) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )


def put_json(key: str, data: dict) -> None:
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data).encode("utf-8"),
    )
