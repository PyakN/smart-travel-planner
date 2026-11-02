"""POST /trips/{id}/edit: change a day of a saved trip as it goes, in the seeded town of
Testville (which keeps UTC). Edits never call the LLM, and answer with a draft."""

import re
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.api.deps import get_now
from app.ingest.cities import CITIES
from tests.fakes import FakeProvider, FakeWeather
from tests.integration.conftest import sign_up
from tests.integration.test_evening_api import OVERNIGHT, PICKS
from tests.integration.test_replace_api import FIRST_DAY, TESTVILLE, create_plan, names
from tests.integration.test_trip_visits_api import visit
from tests.integration.test_trips_api import save
from tests.integration.test_weather_api import WEDNESDAY, weather  # noqa: F401 (fixture)

HOTEL = {"lat": 45.0000, "lon": 7.0030, "round_trip": True}
MONDAY = "2026-11-02"


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


@pytest.fixture
def trip(visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> dict[str, Any]:
    """A logged-in user's saved one-day trip around FIRST_DAY."""
    plan = create_plan(visitor, llm, place_ids, FIRST_DAY)
    sign_up(visitor)
    return save(visitor, plan["id"])


def saved_trip(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], picks: list[str], **body: Any
) -> dict[str, Any]:
    plan = create_plan(client, llm, place_ids, picks, **body)
    sign_up(client)
    return save(client, plan["id"])


def edit(client: TestClient, trip: dict[str, Any], day: int = 1, **body: Any) -> Response:
    return client.post(f"/trips/{trip['id']}/edit", json={"day": day, **body})


def drafted(client: TestClient, trip: dict[str, Any], **body: Any) -> dict[str, Any]:
    response = edit(client, trip, **body)
    assert response.status_code == 201, response.text
    draft: dict[str, Any] = response.json()
    return draft


def stops(plan: dict[str, Any], day: int = 1) -> list[dict[str, Any]]:
    stops_of_day: list[dict[str, Any]] = plan["days"][day - 1]["stops"]
    return stops_of_day


def minutes(clock: str) -> int:
    hours, mins = map(int, clock.split(":"))
    return hours * 60 + mins


def at(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[get_now] = lambda: moment  # type: ignore[attr-defined]


def test_remove_and_add_make_a_draft(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    calls = len(llm.calls)
    tower, park = place_ids["Clock Tower"], place_ids["River Park"]
    draft = drafted(visitor, trip, remove=[tower], add=[park])
    assert len(llm.calls) == calls  # no AI

    assert draft["parent_id"] == trip["plan"]["id"]
    assert draft["edit"] == {
        "day": 1,
        "kind": "edit",
        "replaced": [],
        "removed": [{"place_id": tower, "name": "Clock Tower"}],
        "added": [{"place_id": park, "name": "River Park"}],
        "next": None,
        "after": None,
        "adjustments": [],
        "dropped": [],
        "warnings": [],
    }
    assert sorted(names(draft)) == [
        "Hilltop Viewpoint",
        "Old Town Square",
        "River Park",
        "Testville Cathedral",
    ]
    assert visitor.get(f"/plans/{draft['id']}").json() == draft

    # The trip keeps its plan until the draft is saved; the next edit starts from there.
    path = f"/trips/{trip['id']}"
    assert visitor.get(path).json()["plan"]["id"] == trip["plan"]["id"]
    saved = visitor.patch(path, json={"plan_id": draft["id"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["plan"] == draft
    assert drafted(visitor, trip, remove=[park])["parent_id"] == draft["id"]


def test_a_draft_made_from_an_outdated_version_is_refused(
    visitor: TestClient, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    # Two drafts made from the same version (two tabs): saving one outdates the other.
    first = drafted(visitor, trip, remove=[place_ids["Clock Tower"]])
    second = drafted(visitor, trip, add=[place_ids["River Park"]])
    path = f"/trips/{trip['id']}"
    assert visitor.patch(path, json={"plan_id": first["id"]}).status_code == 200
    refused = visitor.patch(path, json={"plan_id": second["id"]})
    assert refused.status_code == 409
    assert visitor.get(path).json()["plan"]["id"] == first["id"]
    # Undo is still fine: back to the version the current one was made from.
    undone = visitor.patch(path, json={"plan_id": trip["plan"]["id"]})
    assert undone.json()["plan"]["id"] == trip["plan"]["id"]


def test_visited_stops_stay_first_as_they_were(
    visitor: TestClient, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    planned = stops(trip["plan"])
    third, first = planned[2], planned[0]
    visit(visitor, trip, third["place_id"])
    visit(visitor, trip, first["place_id"])
    draft = drafted(visitor, trip, add=[place_ids["River Park"]])
    day = stops(draft)
    assert [s["place_id"] for s in day[:2]] == [first["place_id"], third["place_id"]]
    assert day[0]["arrive"] == first["arrive"]
    assert len(day) == 5

    refused = edit(visitor, trip, remove=[third["place_id"]])
    assert refused.status_code == 422
    assert refused.json()["detail"] == f"{third['name']}: visited places stay on the trip."
    refused = edit(visitor, trip, next=first["place_id"])
    assert refused.json()["detail"] == f"{first['name']} is visited already."


def test_next_stop_from_where_the_traveller_is_now(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start=HOTEL, start_date=MONDAY)
    first = stops(trip["plan"])[0]
    visit(visitor, trip, first["place_id"])
    at(visitor, datetime(2026, 11, 2, 11, 0, 20, tzinfo=UTC))
    market = place_ids["Fish Market"]
    pin = {"lat": 45.0040, "lon": 7.0060}
    draft = drafted(visitor, trip, add=[market], next=market, start=pin, stay_min=20)

    visited, nxt, *rest = stops(draft)
    assert visited["place_id"] == first["place_id"]
    assert nxt["place_id"] == market
    assert nxt["departure"] == {**pin, "time": "11:01"}  # now, rounded up to the minute
    assert minutes(nxt["arrive"]) == minutes("11:01") + nxt["travel_min"]
    assert minutes(nxt["leave"]) - minutes(nxt["arrive"]) == 20
    assert {s["place_id"] for s in rest} == {s["place_id"] for s in stops(trip["plan"])[1:]}
    assert all(s["departure"] is None for s in [visited, *rest])
    assert draft["edit"]["next"] == {"place_id": market, "name": "Fish Market"}
    assert draft["edit"]["added"] == [{"place_id": market, "name": "Fish Market"}]

    # Drawn from the hotel to the visited stop, then from the pin on, and back to the hotel;
    # not the traveller's own way from the visited stop to the pin.
    segments = draft["days"][0]["segments"]
    hotel = [HOTEL["lon"], HOTEL["lat"]]
    assert [s["geometry"][0] for s in segments] == [hotel, [pin["lon"], pin["lat"]]]
    assert segments[-1]["geometry"][-1] == hotel

    # The chosen stay stays with the place in later edits.
    visitor.patch(f"/trips/{trip['id']}", json={"plan_id": draft["id"]})
    newer = drafted(visitor, trip, remove=[rest[0]["place_id"]])
    market_stop = next(s for s in stops(newer) if s["place_id"] == market)
    assert minutes(market_stop["leave"]) - minutes(market_stop["arrive"]) == 20


def test_a_location_on_another_day_plans_from_it_as_the_day_goes(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start_date=MONDAY)
    at(visitor, datetime(2026, 10, 30, 15, 0, tzinfo=UTC))  # days before the trip
    pin = {"lat": 45.0040, "lon": 7.0060}
    first = stops(drafted(visitor, trip, start=pin))[0]
    assert first["departure"] == {**pin, "time": "09:30"}


def test_the_day_is_over(visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> None:
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start_date=MONDAY)
    at(visitor, datetime(2026, 11, 2, 21, 30, tzinfo=UTC))
    refused = edit(visitor, trip, start={"lat": 45.0, "lon": 7.0})
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Day 1 is over: its hours ended at 21:30."


def test_stops_drop_only_when_the_day_runs_long(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # From 16:00 to 03:00: three sights before 20:00, then the bar the traveller put in place
    # of the plan's evening sight (saved, so it is an ordinary stop of the day now).
    trip = saved_trip(visitor, llm, place_ids, PICKS, **OVERNIGHT)
    bar, fado = place_ids["Harbour Bar"], place_ids["Old Town Fado"]
    evening = [s["place_id"] for s in stops(trip["plan"]) if s["hours"] == "any"]
    with_bar = drafted(visitor, trip, remove=evening, add=[bar])
    assert visitor.patch(f"/trips/{trip['id']}", json={"plan_id": with_bar["id"]}).is_success
    assert bar in [s["place_id"] for s in stops(with_bar)] and len(stops(with_bar)) == 4

    # Five hours at a fado house: far longer than the relaxed pace allows (5 h 30 min in
    # all), but the day still ends by 03:00, so nothing is dropped.
    long = drafted(visitor, trip, add=[fado], stay_min=300)
    assert long["edit"]["dropped"] == [] and long["edit"]["warnings"] == []
    assert len(stops(long)) == 5
    assert long["days"][0]["duration_min"] > 330
    assert stops(long)[-1]["leave"] <= "03:00"

    # Seven hours: the bar has to go; the sights before 20:00 stay, they do not delay it.
    longer = drafted(visitor, trip, add=[fado], stay_min=420)
    [dropped] = longer["edit"]["dropped"]
    assert (dropped["place_id"], dropped["name"]) == (bar, "Harbour Bar")
    assert re.fullmatch(r"The day would end at 0[34]:\d\d instead of 03:00\.", dropped["reason"])
    assert {"place_id": bar, "name": "Harbour Bar"} in longer["dropped"]
    assert len(stops(longer)) == 4
    assert longer["edit"]["warnings"] == []

    # Eight hours: too long even alone, but it is what the traveller asked for.
    longest = drafted(visitor, trip, add=[fado], stay_min=480)
    assert fado in [s["place_id"] for s in stops(longest)]
    [warning] = longest["edit"]["warnings"]
    assert re.fullmatch(
        r"Day 1 ends at 0[34]:\d\d instead of 03:00: the places you chose take that long\.",
        warning,
    )


def test_edits_of_weather_aware_days_keep_the_forecast(
    visitor: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    weather: FakeWeather,  # noqa: F811
) -> None:
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start_date=WEDNESDAY, weather_aware=True)
    asked = len(weather.asked)
    planned = {s["place_id"] for s in stops(trip["plan"])}
    indoor = ["City Museum", "Museum of Toys", "Saint Paul Church", "Modern Art Gallery"]
    place = next(place_ids[n] for n in indoor if place_ids[n] not in planned)
    draft = drafted(visitor, trip, add=[place])
    assert len(weather.asked) == asked + 1  # the latest forecast
    assert draft["days"][0]["weather"] is not None
    assert all(s["weather"] is not None for s in stops(draft))


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"remove": ["Fish Market"]}, "Only stops of day 1 can be removed."),
        ({"day": 5, "remove": ["Clock Tower"]}, "Day 5 is not in this plan."),
        ({"add": ["Clock Tower"]}, "Clock Tower is on day 1 already."),
        ({"next": "Praça do Comércio"}, "Place {} is not in Testville."),
        ({"remove": FIRST_DAY}, "Keep at least one stop on day 1."),
        ({}, None),
        ({"remove": ["Clock Tower"], "add": ["Clock Tower"]}, None),
        ({"remove": ["Clock Tower"], "next": "Clock Tower"}, None),
        ({"remove": ["Clock Tower"], "stay_min": 30}, None),
        ({"add": ["River Park"], "stay_min": 2}, None),
        ({"add": ["River Park"], "after": "Clock Tower"}, None),
        ({"next": "Clock Tower", "after": "Clock Tower"}, None),
        ({"remove": ["Clock Tower"], "next": "Old Town Square", "after": "Clock Tower"}, None),
        (
            {"add": ["River Park"], "next": "River Park", "after": "Fish Market"},
            "The next stop can only follow a stop of day 1.",
        ),
    ],
    ids=[
        "not-on-the-day",
        "no-such-day",
        "planned-already",
        "other-city",
        "nothing-left",
        "no-change",
        "remove-and-add",
        "remove-the-next",
        "stay-without-a-place",
        "too-short-a-stay",
        "after-without-a-next-stop",
        "after-itself",
        "after-a-removed-stop",
        "after-a-stop-of-no-day",
    ],
)
def test_invalid_edits(
    visitor: TestClient,
    place_ids: dict[str, int],
    trip: dict[str, Any],
    body: dict[str, Any],
    detail: str | None,
) -> None:
    def ids(value: Any) -> Any:
        if isinstance(value, list):
            return [place_ids[n] for n in value]
        return place_ids[value] if isinstance(value, str) else value

    payload = {"day": 1, **{k: ids(v) for k, v in body.items()}}
    response = visitor.post(f"/trips/{trip['id']}/edit", json=payload)
    assert response.status_code == 422, response.text
    if detail:
        assert response.json()["detail"] == detail.format(payload.get("next"))
    assert visitor.get(f"/trips/{trip['id']}").json()["plan"] == trip["plan"]


def test_only_the_owner_edits(
    visitor: TestClient, place_ids: dict[str, int], trip: dict[str, Any]
) -> None:
    body = {"remove": [place_ids["Clock Tower"]]}
    sign_up(visitor, "Bo")
    assert edit(visitor, trip, **body).status_code == 404
    visitor.cookies.clear()
    assert edit(visitor, trip, **body).status_code == 401


def test_eat_and_drink_on_the_way(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # A round trip from a hotel. Mid-day, two stops visited, the traveller finds a café near
    # where they are and goes there next; later, a bar.
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start=HOTEL, start_date=MONDAY)
    planned = [s["place_id"] for s in stops(trip["plan"])]
    for place_id in planned[:2]:
        visit(visitor, trip, place_id)
    at(visitor, datetime(2026, 11, 2, 12, 30, tzinfo=UTC))
    pin = {"lat": 45.0040, "lon": 7.0060}
    cafe = place_ids["Green Leaf Café"]
    draft = drafted(visitor, trip, add=[cafe], next=cafe, start=pin, stay_min=30)

    day = stops(draft)
    assert [s["place_id"] for s in day[:3]] == [*planned[:2], cafe]
    assert day[2]["departure"] == {**pin, "time": "12:30"}
    assert {s["place_id"] for s in day[3:]} == set(planned[2:])
    hotel = [HOTEL["lon"], HOTEL["lat"]]
    assert draft["days"][0]["segments"][-1]["geometry"][-1] == hotel
    assert stops(draft)[-1]["leave"] <= "21:30"
    assert draft["edit"]["dropped"] == [] and draft["edit"]["warnings"] == []
    assert visitor.patch(f"/trips/{trip['id']}", json={"plan_id": draft["id"]}).is_success

    # A bar keeps the evening as its usual hours, but this one is the next stop: it is
    # visited now, and its own hours say it is open.
    visit(visitor, trip, cafe)
    at(visitor, datetime(2026, 11, 2, 13, 30, tzinfo=UTC))
    bar = place_ids["Harbour Bar"]
    later = drafted(visitor, trip, add=[bar], next=bar, start=pin, stay_min=45)
    day = stops(later)
    assert [s["place_id"] for s in day[:4]] == [*planned[:2], cafe, bar]
    assert day[3]["wait_min"] == 0 and day[3]["arrive"] < "14:00"
    assert minutes(day[3]["leave"]) - minutes(day[3]["arrive"]) == 45
    assert {s["place_id"] for s in day[4:]} == set(planned[2:])
    assert later["edit"]["dropped"] == [] and later["edit"]["warnings"] == []
    assert visitor.patch(f"/trips/{trip['id']}", json={"plan_id": later["id"]}).is_success


def test_a_place_to_eat_right_after_a_stop_of_a_day_ahead(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # Days before the trip, the traveller finds a bar near the second stop. Only added, it
    # waits for the evening, when bars open; as the next stop after the second, it is there.
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start=HOTEL, start_date=MONDAY)
    at(visitor, datetime(2026, 10, 30, 15, 0, tzinfo=UTC))
    planned = stops(trip["plan"])
    bar = place_ids["Harbour Bar"]
    evening = stops(drafted(visitor, trip, add=[bar], stay_min=45))
    assert evening[-1]["place_id"] == bar and evening[-1]["arrive"] >= "20:00"

    second = planned[1]
    draft = drafted(visitor, trip, add=[bar], next=bar, after=second["place_id"], stay_min=45)
    day = stops(draft)
    assert [s["place_id"] for s in day[:3]] == [planned[0]["place_id"], second["place_id"], bar]
    assert [s["arrive"] for s in day[:2]] == [s["arrive"] for s in planned[:2]]  # as planned
    assert day[2]["wait_min"] == 0
    arrive = minutes(day[1]["leave"]) + day[2]["travel_min"]
    assert abs(minutes(day[2]["arrive"]) - arrive) <= 1
    assert {s["place_id"] for s in day[3:]} == {s["place_id"] for s in planned[2:]}
    assert draft["edit"]["next"] == {"place_id": bar, "name": "Harbour Bar"}
    assert draft["edit"]["after"] == {"place_id": second["place_id"], "name": second["name"]}
    assert draft["edit"]["dropped"] == [] and draft["edit"]["warnings"] == []

    # After a visited stop, the next one follows all the visited stops.
    visit(visitor, trip, planned[2]["place_id"])
    visit(visitor, trip, planned[0]["place_id"])
    draft = drafted(visitor, trip, add=[bar], next=bar, after=planned[0]["place_id"])
    first, third = planned[0]["place_id"], planned[2]["place_id"]
    assert [s["place_id"] for s in stops(draft)[:3]] == [first, third, bar]


def test_the_opening_hours_of_places_you_choose(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    trip = saved_trip(visitor, llm, place_ids, FIRST_DAY, start=HOTEL, start_date=MONDAY)
    at(visitor, datetime(2026, 11, 2, 14, 0, tzinfo=UTC))
    pin = {"lat": 45.0040, "lon": 7.0060}
    # The pub opens at 17:00; the vegetarian place closes at 15:00 until dinner.
    pub, garden = place_ids["Corner Pub"], place_ids["Veggie Garden"]
    draft = drafted(visitor, trip, add=[pub], next=pub, start=pin, stay_min=30)
    [warning] = draft["edit"]["warnings"]
    assert re.fullmatch(r"By its opening hours, Corner Pub is closed at 14:0\d\.", warning)

    draft = drafted(visitor, trip, add=[garden], next=garden, start=pin, stay_min=75)
    [warning] = draft["edit"]["warnings"]
    assert warning == "By its opening hours, Veggie Garden closes at 15:00, before the visit ends."
