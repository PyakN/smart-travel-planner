"""POST /trips/{id}/replace: AI replacements on a saved trip keep its visited stops first,
as day edits do, in the seeded town of Testville."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.ingest.cities import CITIES
from app.schemas.trip import PlaceSelection
from tests.fakes import FakeProvider
from tests.integration.conftest import sign_up
from tests.integration.test_day_edit_api import stops
from tests.integration.test_replace_api import FIRST_DAY, TESTVILLE, create_plan, picks
from tests.integration.test_trip_visits_api import visit
from tests.integration.test_trips_api import save
from tests.test_trip_schema import trip as trip_request


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


@pytest.fixture
def trip(visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> dict[str, Any]:
    """A logged-in user's saved one-day trip around FIRST_DAY."""
    plan = create_plan(visitor, llm, place_ids, FIRST_DAY)
    sign_up(visitor)
    return save(visitor, plan["id"])


def replace(
    client: TestClient, trip: dict[str, Any], place_ids: list[int], day: int = 1
) -> Response:
    return client.post(f"/trips/{trip['id']}/replace", json={"day": day, "place_ids": place_ids})


def test_visited_stops_stay_first_as_they_were(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    planned = stops(trip["plan"])
    first, second, third, last = planned
    # Visited out of order: the last stop, then the first.
    visit(visitor, trip, last["place_id"])
    visit(visitor, trip, first["place_id"])
    park = place_ids["River Park"]
    picks(llm, park)
    response = replace(visitor, trip, [second["place_id"]])
    assert response.status_code == 201, response.text
    draft = response.json()

    day = stops(draft)
    # Visited stops first, in their planned order and from the start of the day as before.
    assert [s["place_id"] for s in day[:2]] == [first["place_id"], last["place_id"]]
    assert day[0]["arrive"] == first["arrive"]
    assert {s["place_id"] for s in day[2:]} == {third["place_id"], park}
    assert draft["parent_id"] == trip["plan"]["id"]
    assert draft["edit"]["kind"] == "replace"
    assert draft["edit"]["added"] == [{"place_id": park, "name": "River Park"}]
    assert draft["edit"]["dropped"] == []
    # A draft: the trip uses it once it is saved.
    current = visitor.get(f"/trips/{trip['id']}").json()
    assert current["plan"]["id"] == trip["plan"]["id"]
    saved = visitor.patch(f"/trips/{trip['id']}", json={"plan_id": draft["id"]})
    assert saved.status_code == 200, saved.text


def test_a_trip_without_visits_replaces_as_a_plan_does(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    planned = stops(trip["plan"])
    park = place_ids["River Park"]
    picks(llm, park)
    draft = replace(visitor, trip, [planned[1]["place_id"]]).json()
    picks(llm, park)
    plan = visitor.post(
        f"/plans/{trip['plan']['id']}/replace",
        json={"day": 1, "place_ids": [planned[1]["place_id"]]},
    ).json()
    assert stops(draft) == stops(plan)


def test_visited_stops_cannot_be_replaced(
    visitor: TestClient, llm: FakeProvider, trip: dict[str, Any]
) -> None:
    first = stops(trip["plan"])[0]
    visit(visitor, trip, first["place_id"])
    refused = replace(visitor, trip, [first["place_id"]])
    assert refused.status_code == 422
    assert refused.json()["detail"] == f"{first['name']}: visited places stay on the trip."
    assert not [c for c in llm.calls if "You replace places" in str(c["system"])]


def test_only_the_owner_replaces(
    visitor: TestClient, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    tower = [place_ids["Clock Tower"]]
    sign_up(visitor, "Bo")
    assert replace(visitor, trip, tower).status_code == 404
    visitor.cookies.clear()
    assert replace(visitor, trip, tower).status_code == 401


def test_stops_that_no_longer_fit_after_the_visits_say_why(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # The Museum of Toys closes at 18:00: first in the afternoon, it fits; after the
    # cathedral, visited first, it does not.
    names = ["Museum of Toys", "Testville Cathedral", "Saint Paul Church"]
    llm.queue(
        trip_request(city="testville", days=1, pace="moderate", interests=["museum"]),
        PlaceSelection(place_ids=[place_ids[n] for n in names], rationale="Test."),
    )
    hours = {"start_date": "2026-11-03", "day_start": "16:00", "day_end": "21:30"}
    plan = visitor.post("/plan", json={"text": "Testville", **hours}).json()
    assert [s["name"] for s in stops(plan)][0] == "Museum of Toys"
    assert len(stops(plan)) == 3
    sign_up(visitor)
    trip = save(visitor, plan["id"])
    visit(visitor, trip, place_ids["Testville Cathedral"])
    picks(llm, place_ids["Saint Anne Church"])
    draft = replace(visitor, trip, [place_ids["Saint Paul Church"]]).json()

    day = [s["name"] for s in stops(draft)]
    assert day[0] == "Testville Cathedral"
    assert "Saint Anne Church" in day and "Museum of Toys" not in day
    assert draft["edit"]["added"] == [
        {"place_id": place_ids["Saint Anne Church"], "name": "Saint Anne Church"}
    ]
    assert draft["edit"]["dropped"] == [
        {
            "place_id": place_ids["Museum of Toys"],
            "name": "Museum of Toys",
            "reason": "It would be closed, or dark, by the time you get there.",
        }
    ]
    assert not [w for w in draft["warnings"] if w.startswith("dropped")]
