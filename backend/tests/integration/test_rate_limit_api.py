"""The endpoints that call the LLM are limited per client; the others are not."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_ai_limiter
from app.rate_limit import Limit, RateLimiter
from tests.fakes import FakeProvider


@pytest.fixture
def two_per_minute(client: TestClient, llm: FakeProvider) -> Iterator[TestClient]:
    # With an LLM configured, whatever .env holds: without one the endpoints answer 503.
    limiter = RateLimiter([Limit(2, 60)])
    client.app.dependency_overrides[get_ai_limiter] = lambda: limiter  # type: ignore[attr-defined]
    yield client
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def test_ai_requests_beyond_the_limit_get_429(two_per_minute: TestClient) -> None:
    replace = {"day": 1, "place_ids": [1]}
    for _ in range(2):
        assert two_per_minute.post("/plans/999999/replace", json=replace).status_code == 404
    refused = two_per_minute.post("/plans/999999/replace", json=replace)
    assert refused.status_code == 429
    assert refused.json()["detail"] == "Too many requests to the AI planner. Try again in 1 min."
    assert refused.headers["Retry-After"] == "60"
    # Every endpoint that calls the LLM shares the count.
    assert two_per_minute.post("/plan", json={"text": "a day in Lisbon"}).status_code == 429
    assert two_per_minute.post("/trips/1/replace", json=replace).status_code == 429


def test_other_endpoints_are_not_limited(two_per_minute: TestClient) -> None:
    for _ in range(5):
        assert two_per_minute.get("/cities").status_code == 200
        assert two_per_minute.get("/plans/999999").status_code == 404
