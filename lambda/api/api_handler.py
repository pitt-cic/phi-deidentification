import json
import logging
import re

from handlers import HANDLERS

logger = logging.getLogger("pii_deidentification.api")
logger.setLevel(logging.INFO)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
}

ROUTES = [
    ("GET", r"^/batches$", "list_batches"),
    ("POST", r"^/batches$", "create_batch"),
    ("GET", r"^/batches/(?P<batch_id>[^/]+)$", "get_batch"),
    ("POST", r"^/batches/(?P<batch_id>[^/]+)/start$", "start_batch"),
    ("POST", r"^/batches/(?P<batch_id>[^/]+)/upload-url$", "get_upload_url"),
    ("GET", r"^/batches/(?P<batch_id>[^/]+)/notes$", "list_notes"),
    ("GET", r"^/batches/(?P<batch_id>[^/]+)/notes/(?P<note_id>[^/]+)$", "get_note"),
    ("POST", r"^/batches/(?P<batch_id>[^/]+)/notes/(?P<note_id>[^/]+)/approve$", "approve_note"),
    ("GET", r"^/batches/(?P<batch_id>[^/]+)/notes/(?P<note_id>[^/]+)/download-url$", "get_download_url"),
]


def _match_route(method: str, path: str):
    for route_method, pattern, name in ROUTES:
        if method == route_method:
            m = re.match(pattern, path)
            if m:
                return name, m.groupdict()
    return None, {}


def handler(event, context):
    method = event.get("httpMethod", "")
    path = event.get("path", "")
    logger.info("API request: %s %s", method, path)

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            pass
    query = event.get("queryStringParameters") or {}

    handler_name, params = _match_route(method, path)
    if handler_name is None:
        return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"error": f"No route for {method} {path}"})}

    try:
        status_code, response_body = HANDLERS[handler_name](params, body, query)
    except Exception as e:
        logger.error("Handler error: %s", e, exc_info=True)
        status_code, response_body = 500, {"error": str(e)}

    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(response_body, default=str),
    }
