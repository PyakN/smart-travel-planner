"""POST /plan end to end: real DB and optimizer, scripted LLM, straight-line distances."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_transit
from app.db.models import Route, RouteStop
from app.llm.base import LLMError, TransientLLMError
from app.llm.service import TokenBudget
from app.optimizer.transit import parse_routes
from app.schemas.trip import PlaceNote, PlaceSelection
from tests.fakes import FakeProvider, FakeTransit
from tests.integration.conftest import SEED_DETAILS, SessionFactory, use_llm
from tests.optimizer.test_transit import fixture
from tests.test_trip_schema import trip

ROSSIO = {"lat": 38.7139, "lon": -9.1394}


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
        PlaceSelection(
            place_ids=chosen,
            notes=[PlaceNote(place_id=chosen[0], note="The castle has the best views.")],
            rationale="Views and classics.",
        ),
    )
    return chosen


def path_vertices(day: dict[str, Any]) -> list[list[float]]:
    """All segment vertices in order, without the duplicated joints between segments."""
    vertices: list[list[float]] = []
    for segment in day["segments"]:
        for point in segment["geometry"]:
            if not vertices or vertices[-1] != point:
                vertices.append(point)
    return vertices


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
    assert day["stops"][0]["travel_mode"] is None  # free start
    assert day["stops"][0]["distance_from_previous_m"] == 0
    assert day["self_intersections"] == 0
    # Straight-line test geometry: segments chain through every stop in visiting order.
    assert path_vertices(day) == [[s["lon"], s["lat"]] for s in day["stops"]]
    modes = [s["travel_mode"] for s in day["stops"][1:]]
    assert day["transit_legs"] == modes.count("transit")
    assert {seg["mode"] for seg in day["segments"]} == set(modes)
    assert day["walking_m"] <= day["distance_m"]
    assert plan["total_distance_m"] == day["distance_m"] > 0
    assert plan["distance_source"] == "haversine"
    assert set(plan["timings_ms"]) == {"selection", "optimization", "geometry", "total"}
    notes = {s["place_id"]: s["note"] for s in day["stops"]}
    assert notes.pop(chosen[0]) == "The castle has the best views."
    assert set(notes.values()) == {None}

    # Stop cards: photo, description, hours and website where the place has them.
    by_name = {s["name"]: s for s in day["stops"]}
    castle = SEED_DETAILS["Castelo de São Jorge"]
    assert by_name["Castelo de São Jorge"]["photo"] == {
        "url": castle["image_url"],
        "page_url": castle["image_page_url"],
        "credit": castle["image_credit"],
    }
    assert {
        k: by_name["Castelo de São Jorge"][k] for k in ("description", "opening_hours", "website")
    } == {k: castle[k] for k in ("description", "opening_hours", "website")}
    luzia = by_name["Miradouro de Santa Luzia"]
    assert (luzia["photo"], luzia["description"], luzia["opening_hours"]) == (None, None, None)

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
    assert plan["start"] == {**ROSSIO, "round_trip": True}  # reopened plans show the hotel
    [day] = plan["days"]
    hotel = [ROSSIO["lon"], ROSSIO["lat"]]
    assert day["segments"][0]["geometry"][0] == day["segments"][-1]["geometry"][-1] == hotel
    assert day["stops"][0]["distance_from_previous_m"] > 0


def test_must_visit_and_walking_only(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], db_session: SessionFactory
) -> None:
    torre = place_ids["Torre de Belém"]  # 7 km west of the others
    llm.queue(
        trip(city=None, days=1, pace="relaxed", interests=["viewpoint"]),
        PlaceSelection(
            place_ids=[place_ids[n] for n in ("Castelo de São Jorge", "Miradouro de Santa Luzia")],
            rationale="Views.",
        ),
    )
    response = post_plan(client, must_visit=[torre, torre], modes=["walk"])
    assert response.status_code == 201, response.text
    plan = response.json()

    [day] = plan["days"]
    flagged = {s["place_id"]: s["must_visit"] for s in day["stops"]}
    assert flagged.pop(torre) is True
    assert not any(flagged.values())
    assert day["transit_legs"] == 0  # walking only, even to Belém
    assert plan["modes"] == ["walk"]
    assert plan["must_visit"] == [{"place_id": torre, "name": "Torre de Belém"}]

    async def params() -> dict[str, Any]:
        async with db_session() as session:
            route = await session.get(Route, plan["id"])
            assert route is not None
            return route.params

    stored = asyncio.run(params())
    assert (stored["must_visit"], stored["modes"]) == ([torre], ["walk"])


def test_rides_follow_real_transit_routes(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    route = parse_routes(fixture("figueira_belem"))  # metro Green line, then the Cascais line
    transit = FakeTransit(lambda a, b: route)
    client.app.dependency_overrides[get_transit] = lambda: transit  # type: ignore[attr-defined]
    chosen = [place_ids[n] for n in ("Praça do Comércio", "Castelo de São Jorge", "Torre de Belém")]
    llm.queue(
        trip(city=None, days=1, pace="intense"),
        PlaceSelection(place_ids=chosen, rationale="Classics."),
    )
    response = post_plan(client)
    assert response.status_code == 201, response.text
    plan = response.json()

    assert plan["transit_source"] == "here"
    [day] = plan["days"]
    [ridden] = [s for s in day["stops"] if s["travel_mode"] == "transit"]
    assert [r["line"] for r in ridden["rides"]] == ["Verde", "Linha de Cascais"]
    assert ridden["travel_min"] == 24
    assert [seg["ride"]["line"] for seg in day["segments"] if seg["ride"]] == [
        "Verde",
        "Linha de Cascais",
    ]
    assert len(transit.asked) == 1  # only the leg to (or from) Belém
    assert client.get(f"/plans/{plan['id']}").json() == plan


def test_unknown_must_visit_is_422(client: TestClient, llm: FakeProvider) -> None:
    llm.queue(trip(city=None))
    response = post_plan(client, must_visit=[999999])
    assert response.status_code == 422
    assert response.json()["detail"] == "Some must-visit places are not in Lisbon."


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
    [
        {"text": ""},
        {"text": "x" * 1001},
        {"text": "ok", "start": {"lat": 100, "lon": 0}},
        {"text": "ok", "modes": []},
        {"text": "ok", "modes": ["car"]},
        {"text": "ok", "must_visit": list(range(11))},
    ],
    ids=["empty", "too-long", "bad-start", "no-mode", "bad-mode", "too-many-must-visit"],
)
def test_request_validation(client: TestClient, llm: FakeProvider, body: dict[str, Any]) -> None:
    assert client.post("/plan", json=body).status_code == 422
    assert llm.calls == []  # rejected before any LLM call


def test_missing_plan(client: TestClient) -> None:
    assert client.get("/plans/999999").status_code == 404


def test_outdated_saved_plan_is_404(client: TestClient, db_session: SessionFactory) -> None:
    async def save_old() -> int:
        async with db_session() as session:
            route = Route(city="lisbon", request_text="old", result={"geometry": []})
            session.add(route)
            await session.commit()
            return route.id

    assert client.get(f"/plans/{asyncio.run(save_old())}").status_code == 404
