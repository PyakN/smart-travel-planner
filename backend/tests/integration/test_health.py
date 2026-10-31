from fastapi.testclient import TestClient

from app.llm.service import CircuitBreaker, LLMService
from tests.fakes import FakeProvider


def test_health_reports_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == body["database"] == "ok"


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
