"""Days that run into the night, in the seeded town of Testville (which keeps UTC).

From 16:00 to 03:00 at a relaxed pace a day holds 4 places: 3 before 20:00 and 1 after. The
sun sets in Testville before 16:30 in late October, so none of the 3 can be outdoors.

Plans suggest sights only: the evening gets a sight open at night (Lantern Square, the
Night Market), never Harbour Bar or Old Town Fado unless the traveller picks them.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ingest.cities import CITIES
from app.schemas.trip import PlaceSelection
from app.services.place_selection import VENUE_NOTE
from tests.fakes import FakeProvider
from tests.integration.test_replace_api import (
    TESTVILLE,
    candidate_ids,
    create_plan,
    picks,
    replace,
)
from tests.test_trip_schema import trip

OVERNIGHT = {"start_date": "2026-10-28", "day_start": "16:00", "day_end": "03:00"}
# Two outdoor sights the dark has no room for, and two indoor ones.
PICKS = ["Hilltop Viewpoint", "Old Town Square", "City Museum", "Testville Cathedral"]
VENUES = {"nightlife", "restaurant"}


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


def stops(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [stop for day in plan["days"] for stop in day["stops"]]


def test_an_evening_gets_a_sight_open_at_night(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, PICKS, **OVERNIGHT)

    prompt = str(llm.calls[1]["prompt"])
    assert "When places can be visited" in prompt
    assert ": 3 before 20:00 (at most 0 outdoors), 1 from 20:00" in prompt
    square = place_ids["Lantern Square"]
    assert f"{square} | Lantern Square | landmark, any" in prompt.splitlines()
    assert "Harbour Bar" not in prompt and "Old Town Fado" not in prompt
    assert "Number of places to choose: 4" in prompt

    # The outdoor picks went indoors, and the least important indoor one made way for the
    # square.
    reasons = [s["reason"] for s in plan["hours_swaps"]]
    assert reasons.count("Your hours leave too little daylight for it.") == 2
    assert reasons.count("It closes at 20:00, and more of your day is in the evening.") == 1
    swapped_out = {s["removed"]["name"] for s in plan["hours_swaps"]}
    assert {"Hilltop Viewpoint", "Old Town Square"} <= swapped_out

    planned = stops(plan)
    assert len(planned) == 4 and plan["dropped"] == []
    assert not [s for s in planned if s["hours"] == "daylight" or s["category"] in VENUES]
    assert square in [s["place_id"] for s in planned]
    assert all("16:00" <= s["leave"] <= "20:00" for s in planned if s["hours"] == "day")
    # The rest of the evening is free.
    assert plan["days"][0]["free_from"] == planned[-1]["leave"]
    assert client.get(f"/plans/{plan['id']}").json() == plan


def test_a_day_without_evening_offers_no_bars(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    create_plan(client, llm, place_ids, PICKS)
    prompt = str(llm.calls[1]["prompt"])
    assert "Harbour Bar" not in prompt and "Old Town Fado" not in prompt
    assert "When places can be visited" not in prompt


def test_named_bars_and_restaurants_are_not_suggested(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    bar, fado = place_ids["Harbour Bar"], place_ids["Old Town Fado"]
    llm.queue(
        trip(
            city="testville",
            days=1,
            pace="relaxed",
            interests=["nightlife", "restaurant"],
            keywords=["Harbour Bar", "Fado"],
        ),
        PlaceSelection(place_ids=[bar, fado, place_ids["City Museum"]], rationale="Test."),
    )
    response = client.post("/plan", json={"text": "Bars and fado in Testville", **OVERNIGHT})
    assert response.status_code == 201, response.text
    plan = response.json()

    assert not candidate_ids(llm) & {bar, fado}
    assert not [s for s in stops(plan) if s["category"] in VENUES]
    assert VENUE_NOTE in plan["warnings"]
    assert "dropped 2 id(s) not in the candidate list" in plan["warnings"]


def test_a_must_visit_bar_is_planned_at_night(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    bar = place_ids["Harbour Bar"]
    plan = create_plan(client, llm, place_ids, PICKS, must_visit=[bar], **OVERNIGHT)

    prompt = str(llm.calls[1]["prompt"])
    assert f"- {bar} | Harbour Bar | nightlife, night" in prompt.splitlines()
    assert ": 3 before 20:00 (at most 0 outdoors), 1 from 20:00" in prompt
    assert "Number of places to choose: 3" in prompt
    [evening] = [s for s in stops(plan) if s["hours"] == "night"]
    assert evening["place_id"] == bar and evening["must_visit"]
    assert evening["arrive"] == "20:00" and evening["wait_min"] > 0


def test_an_evening_stop_is_replaced_by_a_sight_open_at_night(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    bar, market = place_ids["Harbour Bar"], place_ids["Night Market"]
    plan = create_plan(client, llm, place_ids, PICKS, must_visit=[bar], **OVERNIGHT)
    picks(llm, market)
    response = replace(client, plan, 1, [bar])
    assert response.status_code == 201, response.text

    prompt = str(llm.calls[-1]["prompt"])
    assert "- Harbour Bar (nightlife, at 20:00)" in prompt
    assert f"{market} | Night Market | market, any" in prompt
    # Food and drink are never offered; places that close at 20:00, or need daylight, cannot
    # take an evening slot.
    sights_open_at_night = {place_ids["Lantern Square"], market}
    assert candidate_ids(llm) <= sights_open_at_night
    assert market in [s["place_id"] for s in stops(response.json())]


def test_an_evening_without_sights_open_at_night_is_free(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # The traveller rejects squares and markets: the evening has nothing, the day keeps its own.
    llm.queue(
        trip(city="testville", days=1, pace="relaxed", avoid=["landmark", "market"]),
        PlaceSelection(place_ids=[place_ids[n] for n in PICKS], rationale="Test."),
    )
    response = client.post("/plan", json={"text": "Testville", **OVERNIGHT})
    assert response.status_code == 201, response.text
    planned = stops(response.json())
    assert not [s for s in planned if s["hours"] == "any" or s["category"] in VENUES]
    assert all(s["leave"] <= "20:00" for s in planned)
