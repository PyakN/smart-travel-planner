"""POST /plan end to end: real DB and optimizer, scripted LLM, straight-line distances."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_distances, get_llm
from app.db.models import RouteStop
from app.llm.base import LLMError, TransientLLMError
from app.llm.service import LLMService, TokenBudget
from app.optimizer.distance import HaversineProvider
from app.schemas.trip import PlaceSelection
from tests.fakes import FakeProvider
from tests.integration.conftest import SessionFactory
from tests.test_trip_schema import trip

ROSSIO = {"lat": 38.7139, "lon": -9.1394}


def use_llm(client: TestClient, provider: FakeProvider, **service_kwargs: Any) -> None:
    service = LLMService(provider, model="fake", max_retries=0, **service_kwargs)
    client.app.dependency_overrides[get_llm] = lambda: service  # type: ignore[attr-defined]


@pytest.fixture
def llm(client: TestClient) -> Iterator[FakeProvider]:
    provider = FakeProvider()
    use_llm(client, provider)
    client.app.dependency_overrides[get_distances] = HaversineProvider  # type: ignore[attr-defined]
    yield provider
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def queue_relaxed_day(llm: FakeProvider, place_ids: dict[str, int]) -> list[int]:
    chosen = [
        place_ids[name]
        for name in (
            "Castelo de São Jorge",
            "Museu Calouste Gulbenkian",
            "Miradouro de Santa Luzia",
            "Praça do Comércio",
        )
    ]
    llm.queue(
        trip(city=None, days=1, pace="relaxed", interests=["viewpoint"]),
        PlaceSelection(place_ids=chosen, rationale="Views and classics."),
    )
    return chosen


def post_plan(client: TestClient, **body: Any) -> Any:
    return client.post("/plan", json={"text": "A slow day in Lisbon", **body})


def test_plan_end_to_end(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], db_session: SessionFactory
) -> None:
    chosen = queue_relaxed_day(llm, place_ids)
    response = post_plan(client)
    assert response.status_code == 201, response.text
    plan = response.json()

    assert plan["city"] == "lisbon"
    assert plan["trip"]["pace"] == "relaxed"
    [day] = plan["days"]
    assert sorted(s["place_id"] for s in day["stops"]) == sorted(chosen)
    assert day["stops"][0]["arrive"] == "09:30"
    assert day["stops"][0]["walk_from_previous_m"] == 0
    assert day["self_intersections"] == 0
    # Straight-line geometry: one [lon, lat] vertex per stop, in visiting order.
    assert day["geometry"] == [[s["lon"], s["lat"]] for s in day["stops"]]
    assert plan["total_distance_m"] == day["distance_m"] > 0
    assert plan["distance_source"] == "haversine"
    assert set(plan["timings_ms"]) == {"selection", "optimization", "geometry", "total"}

    # The plan is persisted: same response from GET, stops stored in visiting order.
    assert client.get(f"/plans/{plan['id']}").json() == plan

    async def stored() -> list[tuple[int, int, int]]:
        async with db_session() as session:
            rows = await session.execute(
                select(RouteStop.day, RouteStop.position, RouteStop.place_id)
                .where(RouteStop.route_id == plan["id"])
                .order_by(RouteStop.position)
            )
            return [tuple(row) for row in rows]  # type: ignore[misc]

    assert asyncio.run(stored()) == [
        (1, position, s["place_id"]) for position, s in enumerate(day["stops"], start=1)
    ]


def test_hotel_round_trip(client: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> None:
    queue_relaxed_day(llm, place_ids)
    plan = post_plan(client, start={**ROSSIO, "round_trip": True}).json()
    [day] = plan["days"]
    hotel = [ROSSIO["lon"], ROSSIO["lat"]]
    assert day["geometry"][0] == day["geometry"][-1] == hotel
    assert day["stops"][0]["walk_from_previous_m"] > 0


def test_unsupported_city_is_a_clear_422(client: TestClient, llm: FakeProvider) -> None:
    llm.queue(trip(city="tokyo"))
    response = post_plan(client)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("'tokyo' is not supported yet")


@pytest.mark.parametrize(
    ("error", "status"),
    [(TransientLLMError("503"), 503), (LLMError("bad key"), 502)],
    ids=["unavailable", "rejected"],
)
def test_llm_failures(client: TestClient, llm: FakeProvider, error: Exception, status: int) -> None:
    llm.queue(error)
    response = post_plan(client)
    assert response.status_code == status
    assert "bad key" not in response.text  # internal details are not leaked


def test_budget_exhausted_is_429(client: TestClient, llm: FakeProvider) -> None:
    use_llm(client, llm, budget=TokenBudget(daily_limit=0))
    assert post_plan(client).status_code == 429


def test_llm_not_configured_is_503(client: TestClient) -> None:
    app: Any = client.app
    original, app.state.llm = app.state.llm, None
    try:
        response = post_plan(client)
    finally:
        app.state.llm = original
    assert response.status_code == 503
    assert response.json()["detail"] == "The AI planner is not configured."


@pytest.mark.parametrize(
    "body",
    [{"text": ""}, {"text": "x" * 1001}, {"text": "ok", "start": {"lat": 100, "lon": 0}}],
    ids=["empty", "too-long", "bad-start"],
)
def test_request_validation(client: TestClient, llm: FakeProvider, body: dict[str, Any]) -> None:
    assert client.post("/plan", json=body).status_code == 422
    assert llm.calls == []  # rejected before any LLM call


def test_missing_plan(client: TestClient) -> None:
    assert client.get("/plans/999999").status_code == 404
