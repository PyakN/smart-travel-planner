import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import create_engine
from app.llm.service import CircuitBreaker, LLMService
from app.main import create_app
from tests.fakes import FakeProvider


def test_health_reports_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == body["database"] == "ok"


async def close_other_connections() -> None:
    """What a hosted database does when it suspends: every open connection is closed."""
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
            )
    finally:
        await engine.dispose()


def test_requests_survive_connections_the_database_closed(database_url: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200  # the pool now holds a connection
        asyncio.run(close_other_connections())
        assert client.get("/health").json()["database"] == "ok"


def test_health_reports_the_llm(client: TestClient) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    configured = state.llm
    circuit = CircuitBreaker(threshold=1)
    try:
        state.llm = None
        assert client.get("/health").json()["llm"] == "not_configured"
        state.llm = LLMService(FakeProvider(), model="fake", circuit=circuit)
        assert client.get("/health").json()["llm"] == "ok"
        circuit.failed()
        assert client.get("/health").json()["llm"] == "unavailable"
    finally:
        state.llm = configured
