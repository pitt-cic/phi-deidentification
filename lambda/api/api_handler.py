import json
import logging

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

import handlers

logger = logging.getLogger("pii_deidentification.api")
logger.setLevel(logging.INFO)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
}

app = APIGatewayRestResolver()


def _parse_body() -> dict:
    raw_body = app.current_event.body
    if not raw_body:
        return {}
    if isinstance(raw_body, (dict, list)):
        return raw_body if isinstance(raw_body, dict) else {}
    try:
        parsed = json.loads(raw_body)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _response(status_code: int, payload: object) -> Response:
    return Response(
        status_code=status_code,
        content_type="application/json",
        headers=CORS_HEADERS,
        body=json.dumps(payload, default=str),
    )


def _invoke(handler_fn, params: dict | None = None) -> Response:
    params = params or {}
    body = _parse_body()
    query = app.current_event.query_string_parameters or {}

    try:
        status_code, response_body = handler_fn(params, body, query)
    except Exception as error:
        logger.error("Handler error: %s", error, exc_info=True)
        status_code, response_body = 500, {"error": str(error)}

    return _response(status_code, response_body)


@app.get("/batches")
def list_batches_route() -> Response:
    return _invoke(handlers.list_batches)


@app.get("/batches/<batch_id>")
def get_batch_route(batch_id: str) -> Response:
    return _invoke(handlers.get_batch, {"batch_id": batch_id})


@app.post("/batches/<batch_id>/start")
def start_batch_route(batch_id: str) -> Response:
    return _invoke(handlers.start_batch, {"batch_id": batch_id})


@app.get("/batches/<batch_id>/notes")
def list_notes_route(batch_id: str) -> Response:
    return _invoke(handlers.list_notes, {"batch_id": batch_id})


@app.post("/batches/<batch_id>/approve-all")
def approve_all_notes_route(batch_id: str) -> Response:
    return _invoke(handlers.approve_all_notes, {"batch_id": batch_id})


@app.get("/batches/<batch_id>/notes/<note_id>")
def get_note_route(batch_id: str, note_id: str) -> Response:
    return _invoke(handlers.get_note, {"batch_id": batch_id, "note_id": note_id})


@app.post("/batches/<batch_id>/notes/<note_id>/approve")
def approve_note_route(batch_id: str, note_id: str) -> Response:
    return _invoke(handlers.approve_note, {"batch_id": batch_id, "note_id": note_id})


@app.not_found
def route_not_found() -> Response:
    method = app.current_event.http_method
    path = app.current_event.path
    return _response(404, {"error": f"No route for {method} {path}"})


def handler(event, context):
    method = event.get("httpMethod", "")
    path = event.get("path", "")
    logger.info("API request: %s %s", method, path)

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    return app.resolve(event, context)
