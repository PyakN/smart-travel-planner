"""Saved trips end to end: save a plan, list and open trips, switch versions, privacy."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import Trip
from app.ingest.cities import CITIES
from tests.fakes import FakeProvider
from tests.integration.conftest import SessionFactory, session_token, sign_up, use_session
from tests.integration.test_replace_api import FIRST_DAY, TESTVILLE, create_plan, picks, replace


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


@pytest.fixture
def plan(visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> dict[str, Any]:
    return create_plan(visitor, llm, place_ids, FIRST_DAY)


def save(client: TestClient, plan_id: int, **body: Any) -> dict[str, Any]:
    response = client.post("/trips", json={"plan_id": plan_id, **body})
    assert response.status_code == 201, response.text
    trip: dict[str, Any] = response.json()
    return trip


def test_save_and_open_a_trip(visitor: TestClient, plan: dict[str, Any]) -> None:
    sign_up(visitor)
    trip = save(visitor, plan["id"])
    assert trip["title"] == "1 day in Testville"
    assert trip["plan"] == plan
    assert visitor.get(f"/trips/{trip['id']}").json() == trip

    [summary] = visitor.get("/trips").json()
    assert summary == {
        "id": trip["id"],
        "title": "1 day in Testville",
        "plan_id": plan["id"],
        "city": "testville",
        "request_text": "Testville",
        "days": 1,
        "start_date": plan["start_date"],
        "created_at": trip["created_at"],
        "updated_at": trip["updated_at"],
    }

    # Saving it again gives the same trip; a title is optional.
    again = visitor.post("/trips", json={"plan_id": plan["id"]})
    assert again.status_code == 200 and again.json()["id"] == trip["id"]
    sign_up(visitor, "Bo")
    assert save(visitor, plan["id"], title="  Testville with Bo ")["title"] == "Testville with Bo"


def test_trips_are_listed_newest_change_first(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    sign_up(visitor)
    first = save(visitor, create_plan(visitor, llm, place_ids, FIRST_DAY)["id"])
    second = save(visitor, create_plan(visitor, llm, place_ids, ["City Museum"])["id"])
    assert [t["id"] for t in visitor.get("/trips").json()] == [second["id"], first["id"]]
    visitor.patch(f"/trips/{first['id']}", json={"title": "Renamed"})
    assert [t["id"] for t in visitor.get("/trips").json()] == [first["id"], second["id"]]


def test_trips_need_a_log_in(visitor: TestClient, plan: dict[str, Any]) -> None:
    for method, path in [
        ("POST", "/trips"),
        ("GET", "/trips"),
        ("GET", "/trips/1"),
        ("PATCH", "/trips/1"),
        ("DELETE", "/trips/1"),
    ]:
        body = {"plan_id": plan["id"]} if method in ("POST", "PATCH") else None
        response = visitor.request(method, path, json=body)
        assert response.status_code == 401, (method, path)


def test_other_users_trips_are_not_found(visitor: TestClient, plan: dict[str, Any]) -> None:
    sign_up(visitor)
    trip = save(visitor, plan["id"])
    owner = session_token(visitor)

    sign_up(visitor, "Bo")
    path = f"/trips/{trip['id']}"
    assert visitor.get(path).status_code == 404
    assert visitor.patch(path, json={"title": "Mine now"}).status_code == 404
    assert visitor.delete(path).status_code == 404
    assert visitor.get("/trips").json() == []

    # The plan itself stays public and read-only: share links work without a log-in.
    visitor.cookies.clear()
    assert visitor.get(f"/plans/{plan['id']}").json() == plan
    use_session(visitor, owner)
    assert visitor.get(path).json()["title"] == trip["title"]


def test_switch_to_another_version(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int], plan: dict[str, Any]
) -> None:
    sign_up(visitor)
    trip = save(visitor, plan["id"])
    path = f"/trips/{trip['id']}"

    # A version made from the trip's plan is saved; then undo goes back to the first one.
    picks(llm, place_ids["River Park"])
    edited = replace(visitor, plan, 1, [place_ids["Clock Tower"]]).json()
    saved = visitor.patch(path, json={"plan_id": edited["id"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["plan"] == edited
    assert saved.json()["updated_at"] > trip["updated_at"]
    assert visitor.get(path).json()["plan"]["id"] == edited["id"]

    picks(llm, place_ids["Fish Market"])
    newer = replace(visitor, edited, 1, [place_ids["River Park"]]).json()
    assert visitor.patch(path, json={"plan_id": plan["id"]}).json()["plan"]["id"] == plan["id"]
    # Any version made from the same first plan belongs to the trip.
    assert visitor.patch(path, json={"plan_id": newer["id"]}).json()["plan"]["id"] == newer["id"]

    other = create_plan(visitor, llm, place_ids, FIRST_DAY)
    for plan_id in (other["id"], 10**9):
        refused = visitor.patch(path, json={"plan_id": plan_id})
        assert refused.status_code == 422
        assert refused.json()["detail"] == f"Plan {plan_id} is not a version of this trip."
    assert visitor.get(path).json()["plan"]["id"] == newer["id"]


def test_rename(visitor: TestClient, plan: dict[str, Any]) -> None:
    sign_up(visitor)
    trip = save(visitor, plan["id"])
    path = f"/trips/{trip['id']}"
    renamed = visitor.patch(path, json={"title": "Lazy Sunday "}).json()
    assert renamed["title"] == "Lazy Sunday"
    assert renamed["plan"]["id"] == plan["id"]
    for body in ({}, {"title": "   "}, {"title": "x" * 101}):
        assert visitor.patch(path, json=body).status_code == 422


def test_delete_a_trip(visitor: TestClient, plan: dict[str, Any]) -> None:
    sign_up(visitor)
    trip = save(visitor, plan["id"])
    assert visitor.delete(f"/trips/{trip['id']}").status_code == 204
    assert visitor.get(f"/trips/{trip['id']}").status_code == 404
    assert visitor.get("/trips").json() == []
    assert visitor.get(f"/plans/{plan['id']}").status_code == 200


def test_save_a_missing_plan(visitor: TestClient) -> None:
    sign_up(visitor)
    response = visitor.post("/trips", json={"plan_id": 10**9})
    assert response.status_code == 404
    assert response.json() == {"detail": "plan not found"}


def test_deleting_the_account_deletes_its_trips(
    visitor: TestClient, plan: dict[str, Any], db_session: SessionFactory
) -> None:
    user = sign_up(visitor)
    save(visitor, plan["id"])
    assert visitor.delete("/auth/me").status_code == 204

    async def trips_left() -> int:
        async with db_session() as session:
            count = await session.scalar(
                select(func.count()).select_from(Trip).where(Trip.user_id == user["id"])
            )
            return count or 0

    assert asyncio.run(trips_left()) == 0
    assert visitor.get(f"/plans/{plan['id']}").status_code == 200
