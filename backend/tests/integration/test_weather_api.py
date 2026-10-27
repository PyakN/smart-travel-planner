"""The weather in POST /plan and POST /plans/{id}/replace, in the seeded town of Testville.

Testville keeps UTC, so the forecast's hours read as they are: on Wed 28 Oct it is dry until
10:30, rains from then until 16:30 (62%, then 91%), and the light is gone at 17:37.
"""

from collections.abc import Iterator, Sequence
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_weather
from app.ingest.cities import CITIES
from app.schemas.trip import Pace, PlaceSelection
from app.services.weather_service import city_point, parse_forecast
from tests.fakes import FakeProvider, FakeWeather
from tests.integration.test_replace_api import TESTVILLE
from tests.test_trip_schema import trip
from tests.test_weather_service import fixture

WEDNESDAY = "2026-10-28"
# Four outdoor places first, then two indoor ones.
OUTDOOR_FIRST = [
    "Old Town Square",
    "Clock Tower",
    "Hilltop Viewpoint",
    "River Park",
    "Testville Cathedral",
    "City Museum",
]


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


@pytest.fixture
def weather(client: TestClient, llm: FakeProvider) -> Iterator[FakeWeather]:
    fake = FakeWeather(parse_forecast(fixture()))
    client.app.dependency_overrides[get_weather] = lambda: fake  # type: ignore[attr-defined]
    yield fake


def create_plan(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    names: Sequence[str],
    *,
    pace: Pace = "relaxed",
    **body: Any,
) -> dict[str, Any]:
    llm.queue(
        trip(city="testville", days=1, pace=pace, interests=["viewpoint"]),
        PlaceSelection(place_ids=[place_ids[n] for n in names], rationale="Test."),
    )
    response = client.post("/plan", json={"text": "Testville", **body})
    assert response.status_code == 201, response.text
    plan: dict[str, Any] = response.json()
    return plan


def stops(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [stop for day in plan["days"] for stop in day["stops"]]


def warned(plan: dict[str, Any]) -> list[str]:
    return [s["name"] for s in stops(plan) if s["weather"] and s["weather"]["warning"]]


def test_without_weather_days_still_have_dates(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, OUTDOOR_FIRST[:4])
    tomorrow = TESTVILLE.today() + timedelta(days=1)
    assert plan["start_date"] == plan["days"][0]["date"] == tomorrow.isoformat()
    assert plan["weather_aware"] is False
    assert plan["days"][0]["weather"] is None
    assert {s["weather"] for s in stops(plan)} == {None}
    assert [s["outdoor"] for s in stops(plan)] == [True] * 4


def test_only_weather_aware_plans_ask_for_the_forecast(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], weather: FakeWeather
) -> None:
    plan = create_plan(client, llm, place_ids, OUTDOOR_FIRST[:4], start_date=WEDNESDAY)
    assert weather.asked == []
    assert plan["days"][0]["weather"] is None
    assert {s["weather"] for s in stops(plan)} == {None}
    assert plan["weather_swaps"] == [] and plan["warnings"] == []
    assert "Weather" not in str(llm.calls[1]["prompt"])


def test_every_day_and_stop_shows_its_forecast(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], weather: FakeWeather
) -> None:
    names = ["Testville Cathedral", "Old Town Square", "Clock Tower", "Hilltop Viewpoint"]
    plan = create_plan(client, llm, place_ids, names, start_date=WEDNESDAY, weather_aware=True)
    assert weather.asked == [city_point(TESTVILLE)]
    [day] = plan["days"]
    assert day["date"] == WEDNESDAY
    forecast = day["weather"]
    # Headed by the worst of the day's hours (09:30 to 21:30), in the 3-hour steps they overlap.
    assert {k: forecast[k] for k in ("condition", "description", "icon", "pop")} == {
        "condition": "rain",
        "description": "moderate rain",
        "icon": "10d",
        "pop": 91,
    }
    assert (forecast["temp_min_c"], forecast["temp_max_c"]) == (15, 17)
    assert (forecast["sunrise"], forecast["sunset"]) == ("07:03", "17:37")
    assert (day["sunrise"], day["sunset"]) == ("07:03", "17:37")  # the plan's daylight too
    assert [s["time"] for s in forecast["slots"]] == ["09:00", "12:00", "15:00", "18:00", "21:00"]
    assert forecast["slots"][1] == {
        "time": "12:00",
        "temp_c": 17,
        "condition": "rain",
        "description": "light rain",
        "icon": "10d",
        "pop": 62,
    }

    by_name = {s["name"]: s for s in stops(plan)}
    first = stops(plan)[0]
    assert first["arrive"] == "09:30" and first["weather"]["time"] == "09:00"
    assert all(s["weather"] is not None for s in stops(plan))
    # Indoor stops get the forecast, but no warning.
    assert by_name["Testville Cathedral"]["weather"]["warning"] is None
    assert {by_name[n]["weather"]["warning"] for n in warned(plan)} <= {
        "Light rain likely (62%)",
        "Moderate rain likely (91%)",
    }


def test_only_the_days_hours_count(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], weather: FakeWeather
) -> None:
    # From 16:00 the morning's rain does not matter; until 03:00 the night's fog does.
    hours = {"start_date": WEDNESDAY, "day_start": "16:00", "day_end": "03:00"}
    plan = create_plan(client, llm, place_ids, OUTDOOR_FIRST[:4], weather_aware=True, **hours)
    prompt = str(llm.calls[1]["prompt"])
    assert "- Day 1, Wed 28 Oct: moderate rain 16:00-16:30 (up to 91%), fog 01:30-03:00;" in prompt
    assert "10:30" not in prompt
    slots = plan["days"][0]["weather"]["slots"]
    assert [s["time"] for s in slots] == ["15:00", "18:00", "21:00", "00:00", "03:00"]


def test_weather_aware_plans_keep_outdoor_stops_out_of_the_rain(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    weather: FakeWeather,
) -> None:
    body = {"start_date": WEDNESDAY, "pace": "moderate"}
    plain = create_plan(client, llm, place_ids, OUTDOOR_FIRST, **body)
    aware = create_plan(client, llm, place_ids, OUTDOOR_FIRST, weather_aware=True, **body)
    assert aware["weather_aware"] is True and plain["days"][0]["weather"] is None

    # Dry daylight is a quarter of the day's 8 hours: room for 2 of the 6 stops outdoors.
    # The least important outdoor picks make way for the best-ranked indoor places left.
    assert [(s["removed"]["name"], s["added"]["name"]) for s in aware["weather_swaps"]] == [
        ("River Park", "Museum of Toys"),
        ("Hilltop Viewpoint", "Saint Anne Church"),
    ]
    assert sum(s["outdoor"] for s in stops(aware)) == 2
    # The dry morning goes to an outdoor stop; the plain plan sends some into the rain.
    first = stops(aware)[0]
    assert first["outdoor"] and first["arrive"] == "09:30" and not first["weather"]["warning"]
    assert warned(aware) == []
    assert any(s["outdoor"] and "10:30" <= s["arrive"] < "16:30" for s in stops(plain))
    assert client.get(f"/plans/{aware['id']}").json() == aware


def test_weather_aware_without_a_forecast(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], weather: FakeWeather
) -> None:
    weather.answer = None
    plan = create_plan(client, llm, place_ids, OUTDOOR_FIRST[:4], weather_aware=True)
    assert plan["warnings"] == ["No weather forecast is available, so the plan ignores it."]
    assert plan["days"][0]["weather"] is None and plan["days"][0]["date"] is not None


def test_weather_aware_past_the_forecast(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], weather: FakeWeather
) -> None:
    plan = create_plan(
        client, llm, place_ids, OUTDOOR_FIRST[:4], weather_aware=True, start_date="2026-11-09"
    )
    assert plan["warnings"] == [
        "No forecast yet for day 1; outdoor stops there only avoid the dark."
    ]
    assert plan["days"][0]["weather"] is None


def test_replacing_stops_keeps_the_weather(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int], weather: FakeWeather
) -> None:
    names = ["Testville Cathedral", "Old Town Square", "City Museum", "Museum of Toys"]
    plan = create_plan(client, llm, place_ids, names, weather_aware=True, start_date=WEDNESDAY)
    llm.queue(PlaceSelection(place_ids=[place_ids["Saint Paul Church"]], rationale=""))
    response = client.post(
        f"/plans/{plan['id']}/replace",
        json={"day": 1, "place_ids": [place_ids["Testville Cathedral"]]},
    )
    assert response.status_code == 201, response.text
    new = response.json()

    prompt = str(llm.calls[-1]["prompt"])
    assert "Weather that day: Wed 28 Oct: moderate rain 10:30-16:30 (up to 91%)" in prompt
    assert f"{place_ids['Saint Paul Church']} | Saint Paul Church | religious, indoor" in prompt
    assert f"{place_ids['River Park']} | River Park | park, outdoor" in prompt

    [day] = new["days"]
    assert day["date"] == WEDNESDAY and day["weather"] == plan["days"][0]["weather"]
    assert all(s["weather"] is not None for s in day["stops"])
    assert new["weather_aware"] is True and new["start_date"] == WEDNESDAY
