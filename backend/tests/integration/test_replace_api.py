"""POST /plans/{id}/replace end to end, in the seeded fictional town of Testville."""

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.geo import BBox
from app.ingest.cities import CITIES, City
from app.llm.base import TransientLLMError
from app.optimizer.distance import HaversineProvider
from app.optimizer.planner import DAY_BUDGET_MIN, Stop, plan_route
from app.schemas.trip import PlaceNote, PlaceSelection
from app.services.ai_fallback import REPLACE_FALLBACK_NOTE
from tests.fakes import FakeProvider
from tests.integration.conftest import SEED_PLACES
from tests.test_trip_schema import trip

TESTVILLE = City("testville", "Testville", BBox(44.99, 6.99, 45.09, 7.10))
FIRST_DAY = ["Testville Cathedral", "Old Town Square", "Clock Tower", "Hilltop Viewpoint"]


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


def create_plan(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    names: Sequence[str],
    *,
    days: int = 1,
    **body: Any,
) -> dict[str, Any]:
    llm.queue(
        trip(city="testville", days=days, pace="relaxed", interests=["viewpoint"]),
        PlaceSelection(place_ids=[place_ids[n] for n in names], rationale="Test."),
    )
    response = client.post("/plan", json={"text": "Testville", **body})
    assert response.status_code == 201, response.text
    plan: dict[str, Any] = response.json()
    return plan


def replace(client: TestClient, plan: dict[str, Any], day: int, place_ids: list[int]) -> Response:
    return client.post(f"/plans/{plan['id']}/replace", json={"day": day, "place_ids": place_ids})


def picks(llm: FakeProvider, *place_ids: int, notes: dict[int, str] | None = None) -> None:
    llm.queue(
        PlaceSelection(
            place_ids=list(place_ids),
            notes=[PlaceNote(place_id=i, note=n) for i, n in (notes or {}).items()],
            rationale="",
        )
    )


def names(plan: dict[str, Any], day: int = 1) -> list[str]:
    return [s["name"] for s in plan["days"][day - 1]["stops"]]


def candidate_ids(llm: FakeProvider) -> set[int]:
    """Ids of the candidates offered in the last replacement prompt."""
    lines = str(llm.calls[-1]["prompt"]).split("Candidates (", 1)[1].splitlines()[1:]
    return {int(line.split(" | ", 1)[0]) for line in lines}


def test_replace_one_stop(client: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    park = place_ids["River Park"]
    picks(llm, park, notes={park: "A green break between the sights."})
    response = replace(client, plan, 1, [place_ids["Clock Tower"]])
    assert response.status_code == 201, response.text
    new = response.json()

    assert new["id"] != plan["id"]
    assert new["parent_id"] == plan["id"]
    assert set(names(new)) == {
        "Testville Cathedral",
        "Old Town Square",
        "River Park",
        "Hilltop Viewpoint",
    }
    assert new["edit"] == {
        "day": 1,
        "kind": "replace",
        "replaced": [{"place_id": place_ids["Clock Tower"], "name": "Clock Tower"}],
        "removed": [],
        "added": [{"place_id": park, "name": "River Park"}],
        "next": None,
        "after": None,
        "adjustments": [],
        "dropped": [],
        "warnings": [],
    }
    river = next(s for s in new["days"][0]["stops"] if s["place_id"] == park)
    assert river["note"] == "A green break between the sights."
    assert new["days"][0]["stops"][0]["arrive"] == "09:30"
    assert new["total_distance_m"] == new["days"][0]["distance_m"]

    # Planned and removed places are not offered; the old version is untouched.
    assert not candidate_ids(llm) & {place_ids[n] for n in FIRST_DAY}
    assert "Removed by the traveller:\n- Clock Tower (landmark)" in str(llm.calls[-1]["prompt"])
    assert names(client.get(f"/plans/{plan['id']}").json()) == names(plan)
    assert client.get(f"/plans/{new['id']}").json() == new


def test_replaces_with_a_ranked_place_when_the_llm_fails(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    llm.queue(TransientLLMError("503"))
    response = replace(client, plan, 1, [place_ids["Clock Tower"]])
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["edit"]["warnings"] == [REPLACE_FALLBACK_NOTE]
    [added] = new["edit"]["added"]
    assert added["place_id"] in candidate_ids(llm)  # one the LLM would have been offered
    assert len(names(new)) == 4
    [stop] = [s for s in new["days"][0]["stops"] if s["place_id"] == added["place_id"]]
    assert stop["note"] is None
    assert new["ai_fallback"] is False  # the plan's own places were the LLM's


def test_replacing_keeps_the_days_hours(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    hours = {"day_start": "13:00", "day_end": "21:30", "start_date": "2026-10-28"}
    plan = create_plan(client, llm, place_ids, ["Testville Cathedral", "City Museum"], **hours)
    church = place_ids["Saint Paul Church"]
    picks(llm, church)
    new = replace(client, plan, 1, [place_ids["Testville Cathedral"]]).json()
    [day] = new["days"]
    assert (day["start"], day["end"]) == ("13:00", "21:30")
    assert day["stops"][0]["arrive"] == "13:00"
    assert church in {s["place_id"] for s in day["stops"]}
    assert day["duration_min"] <= 255  # a relaxed share of 8 h 30 min
    assert (new["day_start"], new["day_end"]) == ("13:00", "21:30")


def test_no_repeats_across_days_or_earlier_swaps(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    eight = [*FIRST_DAY, "City Museum", "Museum of Toys", "River Park", "Saint Anne Church"]
    plan = create_plan(client, llm, place_ids, eight, days=2)
    first_day = plan["days"][0]
    rejected = plan["days"][1]["stops"][0]["place_id"]
    market = place_ids["Fish Market"]

    # The LLM tries a place from day 1 and the one being replaced: both are dropped.
    picks(llm, first_day["stops"][0]["place_id"], rejected, market)
    new = replace(client, plan, 2, [rejected]).json()
    assert new["days"][0] == first_day  # other days are copied unchanged
    day_two = [s["place_id"] for s in new["days"][1]["stops"]]
    assert market in day_two and rejected not in day_two
    assert "dropped 2 id(s) not in the candidate list" in new["warnings"]

    # Swapping the market again cannot bring back the first rejected place.
    picks(llm, rejected)
    newer = replace(client, new, 2, [market]).json()
    offered = candidate_ids(llm)
    assert rejected not in offered and market not in offered
    day_two = [s["place_id"] for s in newer["days"][1]["stops"]]
    assert rejected not in day_two and market not in day_two
    assert len(day_two) == len(new["days"][1]["stops"])  # backfilled from the ranking
    all_stops = [s["place_id"] for d in newer["days"] for s in d["stops"]]
    assert len(all_stops) == len(set(all_stops))


def test_sparse_day_is_filled_as_a_last_resort(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    picks(llm, place_ids["River Park"])  # one place for two removed stops
    new = replace(client, plan, 1, [place_ids["Old Town Square"], place_ids["Clock Tower"]]).json()

    assert len(new["days"][0]["stops"]) == 4
    assert [a["name"] for a in new["edit"]["added"]] == ["River Park"]
    [adjustment] = new["edit"]["adjustments"]
    assert adjustment["removed"] is None
    assert adjustment["reason"] == "Fills free time."
    filler = adjustment["added"]["name"]
    assert filler in names(new)
    assert filler not in {"Old Town Square", "Clock Tower", *FIRST_DAY}


def test_one_note_day_gets_variety_as_a_last_resort(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    day = ["Testville Cathedral", "Saint Anne Church", "Old Town Square", "Hilltop Viewpoint"]
    plan = create_plan(client, llm, place_ids, day)
    picks(llm, place_ids["Saint Paul Church"])  # a third church
    new = replace(client, plan, 1, [place_ids["Old Town Square"]]).json()

    [adjustment] = new["edit"]["adjustments"]
    # The least important unticked church goes; the new one stays.
    assert adjustment["removed"]["name"] == "Saint Anne Church"
    assert adjustment["reason"].startswith("For variety: 3 of the day's 4 stops")
    final = {s["name"]: s["category"] for s in new["days"][0]["stops"]}
    assert "Saint Paul Church" in final and "Saint Anne Church" not in final
    assert final[adjustment["added"]["name"]] != "religious"
    assert list(final.values()).count("religious") == 2


def test_replacing_a_must_visit_place(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    cathedral = place_ids["Testville Cathedral"]
    plan = create_plan(client, llm, place_ids, FIRST_DAY[1:], must_visit=[cathedral])
    assert plan["must_visit"] == [{"place_id": cathedral, "name": "Testville Cathedral"}]
    picks(llm, place_ids["River Park"])
    new = replace(client, plan, 1, [cathedral]).json()
    assert new["must_visit"] == []
    assert not any(s["must_visit"] for s in new["days"][0]["stops"])


@pytest.mark.parametrize(
    ("day", "names_", "status", "detail"),
    [
        (1, ["Fish Market"], 422, "Only stops of day 1 can be replaced."),
        (5, ["Clock Tower"], 422, "Day 5 is not in this plan."),
        (1, [], 422, None),
        (0, ["Clock Tower"], 422, None),
    ],
    ids=["not-on-the-day", "no-such-day", "nothing-ticked", "bad-day"],
)
def test_invalid_replacements(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    day: int,
    names_: list[str],
    status: int,
    detail: str | None,
) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    calls = len(llm.calls)
    response = replace(client, plan, day, [place_ids[n] for n in names_])
    assert response.status_code == status
    if detail:
        assert response.json()["detail"] == detail
    assert len(llm.calls) == calls  # rejected before any LLM call


def test_replace_in_missing_plan(client: TestClient, llm: FakeProvider) -> None:
    response = client.post("/plans/999999/replace", json={"day": 1, "place_ids": [1]})
    assert response.status_code == 404


def test_replacements_fit_the_free_time(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A short day: ~2.5 h of the 3 h 20 min budget are used, so removing a 20-minute
    # viewpoint frees ~70 minutes: not enough for a 90-minute museum.
    monkeypatch.setitem(DAY_BUDGET_MIN, "relaxed", 200)
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    assert len(plan["days"][0]["stops"]) == 4
    picks(llm, place_ids["River Park"])
    new = replace(client, plan, 1, [place_ids["Hilltop Viewpoint"]]).json()

    offered = candidate_ids(llm)
    assert place_ids["River Park"] in offered
    assert not offered & {place_ids["City Museum"], place_ids["Museum of Toys"]}
    assert new["days"][0]["duration_min"] <= 200


def test_replacements_that_do_not_fit_together_are_reported(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # About 2 hours free after removing two stops: each museum fits, both do not.
    monkeypatch.setitem(DAY_BUDGET_MIN, "relaxed", 200)
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    picks(llm, place_ids["City Museum"], place_ids["Museum of Toys"])
    removed = [place_ids["Hilltop Viewpoint"], place_ids["Clock Tower"]]
    new = replace(client, plan, 1, removed).json()

    prompt = str(llm.calls[-1]["prompt"])
    assert "Free time for them: about " in prompt
    assert "museum 90" in prompt
    assert [a["name"] for a in new["edit"]["added"]] == ["City Museum"]
    assert "1 replacement(s) did not fit day 1's 3 h 20 min budget" in new["warnings"]
    assert new["days"][0]["duration_min"] <= 200


def test_filler_that_does_not_fit_is_skipped_for_the_next(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # After the swap below the day is the cathedral, the viewpoint and the park. Leave
    # 92 free minutes: the top candidate, a 90-minute museum, is short enough on paper
    # but not with the walk to it, so the next candidate fills the gap instead.
    remaining = [("Testville Cathedral", "religious"), ("Hilltop Viewpoint", "viewpoint")]
    remaining.append(("River Park", "park"))
    coords = {s[2]: (s[4], s[5]) for s in SEED_PLACES}
    stops = [
        Stop(i, *coords[name], category, priority=i) for i, (name, category) in enumerate(remaining)
    ]
    probe = asyncio.run(
        plan_route(
            stops, days=1, pace="relaxed", provider=HaversineProvider(), enforce_budget=False
        )
    )
    monkeypatch.setitem(DAY_BUDGET_MIN, "relaxed", probe.days[0].total_min + 92)

    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    picks(llm, place_ids["River Park"])  # one place for two removed stops
    new = replace(client, plan, 1, [place_ids["Old Town Square"], place_ids["Clock Tower"]]).json()

    first_candidate = str(llm.calls[-1]["prompt"]).split("hint):\n", 1)[1].split(" | ")[1]
    assert first_candidate == "City Museum"
    [adjustment] = new["edit"]["adjustments"]
    assert adjustment["reason"] == "Fills free time."
    assert adjustment["added"]["name"] != "City Museum"
    assert "City Museum" not in names(new)
    assert len(new["days"][0]["stops"]) == 4


def test_stops_the_day_loses_are_listed_with_why(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    monkeypatch.setitem(DAY_BUDGET_MIN, "relaxed", 60)  # too short for the stops that stay
    new = replace(client, plan, 1, [place_ids["Clock Tower"]]).json()

    dropped = new["edit"]["dropped"]
    assert dropped
    assert {d["reason"] for d in dropped} == {"It does not fit day 1's 1 h budget."}
    lost = {d["place_id"] for d in dropped}
    assert lost <= {d["place_id"] for d in new["dropped"]}
    assert not lost & {s["place_id"] for s in new["days"][0]["stops"]}
