"""Days that run into the night, in the seeded town of Testville (which keeps UTC).

From 16:00 to 03:00 at a relaxed pace a day holds 4 places: 3 before 20:00 and 1 after. The
sun sets in Testville before 16:30 in late October, so none of the 3 can be outdoors.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ingest.cities import CITIES
from app.schemas.trip import PlaceSelection
from tests.fakes import FakeProvider
from tests.integration.test_replace_api import TESTVILLE, create_plan, picks, replace
from tests.test_trip_schema import trip

OVERNIGHT = {"start_date": "2026-10-28", "day_start": "16:00", "day_end": "03:00"}
# Two outdoor sights the dark has no room for, and two indoor ones.
PICKS = ["Hilltop Viewpoint", "Old Town Square", "City Museum", "Testville Cathedral"]


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


def stops(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [stop for day in plan["days"] for stop in day["stops"]]


def test_an_evening_gets_places_open_at_night(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, PICKS, **OVERNIGHT)

    prompt = str(llm.calls[1]["prompt"])
    assert "When places can be visited" in prompt
    assert ": 3 before 20:00 (at most 0 outdoors), 1 from 20:00" in prompt
    bar = place_ids["Harbour Bar"]
    assert f"{bar} | Harbour Bar | nightlife, night" in prompt.splitlines()
    assert "Number of places to choose: 4" in prompt

    # The outdoor picks went indoors, and the least important indoor one made way for the bar.
    reasons = [s["reason"] for s in plan["hours_swaps"]]
    assert reasons.count("Your hours leave too little daylight for it.") == 2
    assert reasons.count("It closes at 20:00, and more of your day is in the evening.") == 1
    swapped_out = {s["removed"]["name"] for s in plan["hours_swaps"]}
    assert {"Hilltop Viewpoint", "Old Town Square"} <= swapped_out

    planned = stops(plan)
    assert len(planned) == 4 and plan["dropped"] == []
    assert not [s for s in planned if s["hours"] == "daylight"]
    evening = [s for s in planned if s["hours"] == "night"]
    assert [s["place_id"] for s in evening] == [bar]
    assert evening[0]["arrive"] == "20:00" and evening[0]["wait_min"] > 0
    assert all("16:00" <= s["leave"] <= "20:00" for s in planned if s["hours"] == "day")
    assert client.get(f"/plans/{plan['id']}").json() == plan


def test_a_day_without_evening_offers_no_bars(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    create_plan(client, llm, place_ids, PICKS)
    prompt = str(llm.calls[1]["prompt"])
    assert "Harbour Bar" not in prompt and "Old Town Fado" not in prompt
    assert "When places can be visited" not in prompt


def test_an_evening_stop_is_replaced_by_one_open_at_night(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, PICKS, **OVERNIGHT)
    fado = place_ids["Old Town Fado"]
    picks(llm, fado)
    response = replace(client, plan, 1, [place_ids["Harbour Bar"]])
    assert response.status_code == 201, response.text

    prompt = str(llm.calls[-1]["prompt"])
    assert "- Harbour Bar (nightlife, at 20:00)" in prompt
    assert f"{fado} | Old Town Fado | restaurant, night" in prompt
    # Places that close at 20:00, or need daylight, cannot take an evening slot.
    assert f"{place_ids['Museum of Toys']} | Museum of Toys" not in prompt
    evening = [s for s in stops(response.json()) if s["hours"] == "night"]
    assert [s["place_id"] for s in evening] == [fado]
    assert evening[0]["arrive"] >= "20:00"


def test_selection_without_a_place_for_the_evening(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # The traveller rejects evening places: the evening has nothing, the day keeps its own.
    llm.queue(
        trip(city="testville", days=1, pace="relaxed", avoid=["nightlife", "restaurant"]),
        PlaceSelection(place_ids=[place_ids[n] for n in PICKS], rationale="Test."),
    )
    response = client.post("/plan", json={"text": "Testville", **OVERNIGHT})
    assert response.status_code == 201, response.text
    planned = stops(response.json())
    assert not [s for s in planned if s["hours"] == "night"]
    assert all(s["leave"] <= "20:00" for s in planned)
