"""Structured logs and request ids.

Every record goes through one handler on the root logger, uvicorn's included: one JSON
object per line (`LOG_FORMAT=json`, for log collectors) or a readable line (`text`, the
default). Fields passed in `extra` become JSON fields (`key=value` in text).

Every HTTP request gets an id: the caller's `X-Request-ID` when it looks like one (a
proxy's), else a new one. Each record logged while the request runs carries it, the
response returns it in the same header, and the request is logged once it is answered
(method, path, status, duration), so an error a user reports leads to its log lines.
"""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal, TextIO

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# A caller's id is kept only when short and plain, so it cannot forge log lines.
_CALLER_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
# Polled by load balancers: answered quietly.
QUIET_PATHS = frozenset({"/health"})

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# What every LogRecord has; anything else came in `extra` (uvicorn adds a colored copy of
# its messages).
_RECORD_FIELDS = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "request_id",
    "color_message",
}

logger = logging.getLogger("app.requests")


class RequestIdFilter(logging.Filter):
    """Stamps every record with the id of the request it was logged for (None outside)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in vars(record).items() if k not in _RECORD_FIELDS}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (rid := getattr(record, "request_id", None)) is not None:
            entry["request_id"] = rid
        entry.update(extra_fields(record))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """`2026-10-31 12:00:00,123 INFO app.requests [id] POST /plan 201 status=201 ...`"""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, "request_id", None) is None:
            record.request_id = "-"
        line = super().format(record)
        fields = " ".join(f"{k}={v}" for k, v in extra_fields(record).items())
        if not fields:
            return line
        first, newline, rest = line.partition("\n")  # a traceback stays below
        return f"{first} {fields}{newline}{rest}"


class _AppHandler(logging.StreamHandler[TextIO]):
    """The handler configure_logging installs, told apart from others to replace it."""


def configure_logging(level: str = "INFO", fmt: Literal["json", "text"] = "text") -> None:
    """Send every record, uvicorn's included, through one handler; calling it again
    replaces that handler."""
    handler = _AppHandler()
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    for old in [h for h in root.handlers if isinstance(h, _AppHandler)]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level.upper())
    # uvicorn has handlers of its own; through ours its lines get the format and the ids.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    # RequestContext logs each request, with its id and duration.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def _caller_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            text = value.decode("latin-1")
            return text if _CALLER_ID.fullmatch(text) else None
    return None


class RequestContext:
    """ASGI middleware: the request's id (see the module docstring) and its log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = _caller_id(scope) or uuid.uuid4().hex
        # Not reset afterwards: each request runs in a task of its own, and the error
        # handler and uvicorn's error log, which run after this returns, still need it.
        request_id.set(rid)
        started = time.perf_counter()
        status = 500  # unless a response starts

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, rid)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            path = scope["path"]
            client = scope.get("client")
            logger.log(
                logging.DEBUG if path in QUIET_PATHS and status < 400 else logging.INFO,
                "%s %s %d",
                scope["method"],
                path,
                status,
                extra={
                    "method": scope["method"],
                    "path": path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "client": client[0] if client else None,
                },
            )


async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    """The 500 answer, with the request's id: it is sent outside RequestContext. uvicorn
    logs the traceback."""
    rid = request_id.get()
    return JSONResponse(
        {"detail": "Something went wrong on our side."},
        status_code=500,
        headers={REQUEST_ID_HEADER: rid} if rid else None,
    )


def add_request_context(app: FastAPI) -> None:
    app.add_middleware(RequestContext)
    app.add_exception_handler(Exception, _internal_error)
