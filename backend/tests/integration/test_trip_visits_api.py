"""Visited places of a saved trip: tick and untick stops, and keep them in every version."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ingest.cities import CITIES
from tests.fakes import FakeProvider
from tests.integration.conftest import sign_up
from tests.integration.test_replace_api import FIRST_DAY, TESTVILLE, create_plan, picks, replace
from tests.integration.test_trips_api import save


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


@pytest.fixture
def trip(visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> dict[str, Any]:
    """A logged-in user's saved one-day trip around FIRST_DAY."""
    plan = create_plan(visitor, llm, place_ids, FIRST_DAY)
    sign_up(visitor)
    return save(visitor, plan["id"])


def visit(client: TestClient, trip: dict[str, Any], place_id: int) -> Any:
    return client.put(f"/trips/{trip['id']}/visits/{place_id}")


def visited(client: TestClient, trip: dict[str, Any]) -> list[str]:
    return [v["name"] for v in client.get(f"/trips/{trip['id']}").json()["visits"]]


def test_tick_stops_visited(
    visitor: TestClient, trip: dict[str, Any], place_ids: dict[str, int]
) -> None:
    assert trip["visits"] == []
    square, tower = place_ids["Old Town Square"], place_ids["Clock Tower"]
    first = visit(visitor, trip, square)
    assert first.status_code == 200, first.text
    assert first.json()["place_id"] == square and first.json()["name"] == "Old Town Square"
    visit(visitor, trip, tower)
    assert visited(visitor, trip) == ["Old Town Square", "Clock Tower"]

    # Ticking again keeps the first time; unticking is fine twice.
    assert visit(visitor, trip, square).json() == first.json()
    assert visitor.delete(f"/trips/{trip['id']}/visits/{square}").status_code == 204
    assert visitor.delete(f"/trips/{trip['id']}/visits/{square}").status_code == 204
    assert visited(visitor, trip) == ["Clock Tower"]
    [latest] = visitor.get("/trips").json()
    assert latest["updated_at"] > trip["updated_at"]  # used today: top of the list


def test_only_stops_of_the_trip_can_be_visited(
    visitor: TestClient, trip: dict[str, Any], place_ids: dict[str, int]
) -> None:
    for place_id in (place_ids["Far Fort"], 10**9):
        response = visit(visitor, trip, place_id)
        assert response.status_code == 422
        assert response.json() == {"detail": f"Place {place_id} is not a stop of this trip."}
    assert visited(visitor, trip) == []


def test_only_the_owner_ticks(
    visitor: TestClient, trip: dict[str, Any], place_ids: dict[str, int]
) -> None:
    square = place_ids["Old Town Square"]
    path = f"/trips/{trip['id']}/visits/{square}"
    sign_up(visitor, "Bo")
    assert visitor.put(path).status_code == 404
    assert visitor.delete(path).status_code == 404
    visitor.cookies.clear()
    assert visitor.put(path).status_code == 401
    assert visitor.delete(path).status_code == 401


def test_versions_keep_visited_stops(
    visitor: TestClient, llm: FakeProvider, trip: dict[str, Any], place_ids: dict[str, int]
) -> None:
    tower = place_ids["Clock Tower"]
    visit(visitor, trip, tower)
    visit(visitor, trip, place_ids["Old Town Square"])
    picks(llm, place_ids["River Park"])
    edited = replace(visitor, trip["plan"], 1, [tower]).json()
    assert tower not in {s["place_id"] for s in edited["days"][0]["stops"]}

    path = f"/trips/{trip['id']}"
    refused = visitor.patch(path, json={"plan_id": edited["id"]})
    assert refused.status_code == 409
    assert refused.json() == {"detail": "That version leaves out places you visited: Clock Tower."}
    assert visitor.get(path).json()["plan"]["id"] == trip["plan"]["id"]

    visitor.delete(f"{path}/visits/{tower}")
    saved = visitor.patch(path, json={"plan_id": edited["id"]})
    assert saved.status_code == 200, saved.text
    assert [v["name"] for v in saved.json()["visits"]] == ["Old Town Square"]
