import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
logger = logging.getLogger("repobrain.requests")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **getattr(record, "event_fields", {}),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(level: int) -> None:
    application_logger = logging.getLogger("repobrain")
    if not application_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        application_logger.addHandler(handler)
    application_logger.setLevel(level)
    application_logger.propagate = False


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
            }
        },
        headers=headers,
    )


class RequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_id = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = (
            supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid4().hex
        )
        scope.setdefault("state", {})["request_id"] = request_id
        status_code: int | None = None
        started_at = perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            if status_code is not None:
                # The server must terminate a response that has already started.
                raise
            # Driver exceptions can include failed row contents.
            logger.error(
                "request_failed",
                exc_info=not isinstance(exc, SQLAlchemyError),
                extra={
                    "event_fields": {
                        "request_id": request_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            response = error_response(
                Request(scope), 500, "internal_error", "Internal server error"
            )
            await response(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request_completed",
                extra={
                    "event_fields": {
                        "request_id": request_id,
                        "method": scope["method"],
                        "status_code": status_code,
                        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                    }
                },
            )
