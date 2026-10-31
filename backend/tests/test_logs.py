import json
import logging
import sys
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.logs import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    add_request_context,
    configure_logging,
    request_id,
)

logger = logging.getLogger("tests.logs")


def record(message: str = "plan %d created", *args: object, **extra: object) -> logging.LogRecord:
    entry = logger.makeRecord(logger.name, logging.INFO, __file__, 1, message, args, None)
    entry.__dict__.update(extra)
    return entry


def test_json_lines_carry_the_request_id_and_extra_fields() -> None:
    line = JsonFormatter().format(record("plan %d created", 7, request_id="abc", city="lisbon"))
    entry = json.loads(line)
    assert entry["message"] == "plan 7 created"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "tests.logs"
    assert entry["request_id"] == "abc"
    assert entry["city"] == "lisbon"
    assert entry["time"].endswith("+00:00")


def test_json_lines_keep_the_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        entry = logger.makeRecord(
            logger.name, logging.ERROR, __file__, 1, "failed", (), exc_info=sys.exc_info()
        )
    assert "ValueError: boom" in json.loads(JsonFormatter().format(entry))["exception"]


def test_text_lines_show_the_request_id_and_extra_fields() -> None:
    line = TextFormatter().format(record("plan %d created", 7, request_id="abc", city="lisbon"))
    assert line.endswith("INFO tests.logs [abc] plan 7 created city=lisbon")
    assert "[-] plan 1 created" in TextFormatter().format(record("plan %d created", 1))


def test_configure_logging_replaces_its_own_handler() -> None:
    root = logging.getLogger()
    before = list(root.handlers), root.level
    try:
        configure_logging("debug", "json")
        configure_logging("info", "text")
        ours = [h for h in root.handlers if h not in before[0]]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, TextFormatter)
        assert root.level == logging.INFO
    finally:
        root.handlers[:] = before[0]
        root.setLevel(before[1])


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    add_request_context(app)

    @app.get("/echo")
    async def echo() -> dict[str, str | None]:
        logger.info("inside")
        return {"request_id": request_id.get()}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    return app


@pytest.fixture
def captured(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Log records with the request id stamped on them, as the app's handler has them."""
    stamp = RequestIdFilter()
    caplog.handler.addFilter(stamp)
    caplog.set_level(logging.INFO)
    yield caplog
    caplog.handler.removeFilter(stamp)


def test_every_request_gets_an_id(app: FastAPI, captured: pytest.LogCaptureFixture) -> None:
    response = TestClient(app).get("/echo")
    rid = response.headers[REQUEST_ID_HEADER]
    assert len(rid) == 32
    assert response.json() == {"request_id": rid}
    inside = next(r for r in captured.records if r.getMessage() == "inside")
    assert inside.request_id == rid  # type: ignore[attr-defined]


def test_a_callers_id_is_kept(app: FastAPI) -> None:
    response = TestClient(app).get("/echo", headers={REQUEST_ID_HEADER: "edge-42.a:b"})
    assert response.headers[REQUEST_ID_HEADER] == "edge-42.a:b"


@pytest.mark.parametrize("forged", ["two words", "x" * 65, "a\tb", ""])
def test_an_odd_callers_id_is_replaced(app: FastAPI, forged: str) -> None:
    response = TestClient(app).get("/echo", headers={REQUEST_ID_HEADER: forged})
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_each_request_is_logged_once_answered(
    app: FastAPI, captured: pytest.LogCaptureFixture
) -> None:
    response = TestClient(app).get("/echo?q=1")
    [line] = [r for r in captured.records if r.name == "app.requests"]
    assert line.getMessage() == "GET /echo 200"
    assert line.status == 200  # type: ignore[attr-defined]
    assert line.path == "/echo"  # type: ignore[attr-defined]
    assert line.duration_ms >= 0  # type: ignore[attr-defined]
    assert line.request_id == response.headers[REQUEST_ID_HEADER]  # type: ignore[attr-defined]


def test_an_unexpected_error_answers_500_with_the_id(
    app: FastAPI, captured: pytest.LogCaptureFixture
) -> None:
    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side."}
    rid = response.headers[REQUEST_ID_HEADER]
    [line] = [r for r in captured.records if r.name == "app.requests"]
    assert line.getMessage() == "GET /boom 500"
    assert line.request_id == rid  # type: ignore[attr-defined]
