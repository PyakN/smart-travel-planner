import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.config import Settings
from app.ingest.cities import CITIES
from app.optimizer.geometry import LatLon
from app.services.weather_service import (
    Forecast,
    OpenWeatherProvider,
    WeatherStep,
    city_point,
    city_trip_weather,
    condition,
    create_weather_provider,
    day_forecast,
    day_weather,
    describe_day,
    outdoor_warning,
    parse_forecast,
    stop_forecast,
    trip_weather,
)

# In the shape of OpenWeatherMap's 5 day / 3 hour forecast: Lisbon on Wed 28 Oct 2026
# (UTC+0) with rain from noon, then Thu 29 Oct with fog at dawn and sun after.
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openweather"
LISBON_TZ = ZoneInfo("Europe/Lisbon")
WEDNESDAY, THURSDAY = date(2026, 10, 28), date(2026, 10, 29)
API_KEY = "test-key-not-real"


def fixture(name: str = "lisbon_2026-10-28") -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return body


def forecast() -> Forecast:
    return parse_forecast(fixture())


def step(**overrides: Any) -> WeatherStep:
    values: dict[str, Any] = {
        "time": datetime(2026, 10, 28, 12, tzinfo=UTC),
        "temp_c": 18.0,
        "condition": "clear",
        "description": "clear sky",
        "icon": "01d",
        "pop": 0.0,
        "precipitation_mm": 0.0,
        "visibility_m": 10000,
    }
    return WeatherStep(**{**values, **overrides})


def test_parses_the_forecast() -> None:
    parsed = forecast()
    assert len(parsed.steps) == 16
    assert parsed.sunrise == datetime(2026, 10, 28, 7, 3, 12, tzinfo=UTC)
    assert parsed.sunset == datetime(2026, 10, 28, 17, 37, 48, tzinfo=UTC)
    rain = parsed.steps[5]  # 15:00
    assert rain.time == datetime(2026, 10, 28, 15, tzinfo=UTC)
    assert (rain.condition, rain.description, rain.icon) == ("rain", "moderate rain", "10d")
    assert (rain.temp_c, rain.pop, rain.precipitation_mm, rain.visibility_m) == (
        16.9,
        0.91,
        3.41,
        7400,
    )
    assert parsed.steps[0].precipitation_mm == 0.0  # no "rain" key when it is dry
    assert parsed.steps[9].condition == "fog"


def test_snow_counts_as_precipitation() -> None:
    body = fixture()
    body["list"][0]["snow"] = {"3h": 1.5}
    body["list"][0]["rain"] = {"3h": 0.5}
    assert parse_forecast(body).steps[0].precipitation_mm == 2.0


@pytest.mark.parametrize(
    ("weather_id", "expected"),
    [
        (211, "thunderstorm"),
        (300, "drizzle"),
        (502, "rain"),
        (601, "snow"),
        (701, "fog"),
        (741, "fog"),
        (800, "clear"),
        (801, "clouds"),
        (804, "clouds"),
    ],
)
def test_conditions(weather_id: int, expected: str) -> None:
    assert condition(weather_id) == expected


@pytest.mark.parametrize(
    ("overrides", "badness"),
    [
        ({}, 0.0),
        ({"condition": "clouds", "pop": 0.3}, 0.0),  # a chance of rain, but none forecast
        ({"condition": "rain", "pop": 0.8, "precipitation_mm": 2.0}, 0.8),
        ({"condition": "clouds", "pop": 0.6, "precipitation_mm": 0.2}, 0.6),
        ({"condition": "snow", "pop": 0.9}, 0.9),
        ({"condition": "fog", "visibility_m": 300}, 1.0),
        ({"condition": "fog", "visibility_m": 2500}, 0.5),
        ({"condition": "clouds", "visibility_m": 3000}, 0.5),  # haze
        ({"visibility_m": None}, 0.0),
    ],
)
def test_outdoor_badness(overrides: dict[str, Any], badness: float) -> None:
    assert step(**overrides).outdoor_badness == badness


def test_a_day_in_local_minutes() -> None:
    day = day_weather(forecast(), WEDNESDAY, LISBON_TZ)
    assert (day.sunrise_min, day.sunset_min) == (7 * 60 + 3, 17 * 60 + 37)
    # The day's eight steps and the first of the next day (it covers 22:30 to midnight).
    assert [minute for minute, _ in day.steps] == [h * 60 for h in range(0, 25, 3)]
    assert day.has_forecast

    def described(hour: float) -> str | None:
        found = day.at(hour * 60)
        return found.description if found else None

    assert described(7.5) == "scattered clouds"  # the 09:00 step covers 07:30 to 10:30
    assert described(7.49) == "mist"
    assert described(13) == "light rain"
    assert described(16) == "moderate rain"
    assert day.outdoor_badness(10 * 60) == 0.0
    assert day.outdoor_badness(13 * 60) == 0.62
    assert day.outdoor_badness(16 * 60) == 0.91
    assert day.outdoor_badness(6.5 * 60) == 1.0  # mist, but above all still dark
    assert day.outdoor_badness(19 * 60) == 1.0  # after sunset


def test_later_days_reuse_sunrise_and_sunset() -> None:
    day = day_weather(forecast(), THURSDAY, LISBON_TZ)
    assert (day.sunrise_min, day.sunset_min) == (7 * 60 + 3, 17 * 60 + 37)
    assert day.outdoor_badness(7.25 * 60) == 1.0  # fog after sunrise
    assert day.outdoor_badness(10 * 60) == 0.0


def test_sunrise_follows_daylight_saving_time() -> None:
    # Sunrise at 07:59 summer time on Sat 24 Oct; the clocks go back on Sunday.
    summer = Forecast(
        (), datetime(2026, 10, 24, 6, 59, tzinfo=UTC), datetime(2026, 10, 24, 17, 41, tzinfo=UTC)
    )
    assert day_weather(summer, date(2026, 10, 24), LISBON_TZ).sunrise_min == 7 * 60 + 59
    assert day_weather(summer, date(2026, 10, 26), LISBON_TZ).sunrise_min == 6 * 60 + 59


def test_past_the_forecast_only_darkness_counts() -> None:
    day = day_weather(forecast(), date(2026, 11, 3), LISBON_TZ)
    assert not day.has_forecast
    assert day.at(12 * 60) is None
    assert day.outdoor_badness(12 * 60) == 0.0
    assert day.outdoor_badness(20 * 60) == 1.0


def test_outdoor_share_of_the_sightseeing_hours() -> None:
    trip = trip_weather(forecast(), WEDNESDAY, 2, LISBON_TZ)
    assert [d.date for d in trip.days] == [WEDNESDAY, THURSDAY]
    nine_thirty, half_past_five = 9 * 60 + 30, 17 * 60 + 30
    # Wednesday: dry until 10:30 and from 16:30 (a 47% chance is not bad yet).
    assert (
        trip_weather(forecast(), WEDNESDAY, 1, LISBON_TZ).outdoor_share(nine_thirty, half_past_five)
        == 120 / 480
    )
    assert trip.outdoor_share(nine_thirty, half_past_five) == (120 + 480) / 960
    # An evening past sunset is dark however dry it is.
    assert (
        trip_weather(forecast(), THURSDAY, 1, LISBON_TZ).outdoor_share(17 * 60, 19 * 60) == 37 / 120
    )


def test_describe_day() -> None:
    wednesday, thursday = trip_weather(forecast(), WEDNESDAY, 2, LISBON_TZ).days
    nine_thirty, half_past_seven = 9 * 60 + 30, 19 * 60 + 30
    assert describe_day(wednesday, nine_thirty, half_past_seven) == (
        "Wed 28 Oct: moderate rain 10:30-16:30 (up to 91%); 16-17 °C; daylight 07:03-17:37"
    )
    assert describe_day(thursday, 0, 9 * 60) == (
        "Thu 29 Oct: fog 01:30-07:30; 14-17 °C; daylight 07:03-17:37"
    )
    assert describe_day(thursday, nine_thirty, half_past_seven).startswith("Thu 29 Oct: dry; ")
    later = day_weather(forecast(), date(2026, 11, 3), LISBON_TZ)
    assert describe_day(later, nine_thirty, half_past_seven) == (
        "Tue 3 Nov: no forecast yet; daylight 07:03-17:37"
    )


@pytest.mark.parametrize(
    ("day", "hours", "warning"),
    [
        (WEDNESDAY, (9.5, 10.25), None),  # dry morning
        (WEDNESDAY, (12, 12.75), "Light rain likely (62%)"),
        (WEDNESDAY, (13, 13.75), "Moderate rain likely (91%)"),  # the worst step it meets
        (WEDNESDAY, (16.75, 17.5), None),  # a 47% chance is not bad yet
        (WEDNESDAY, (17.5, 18.25), "After sunset (17:37)"),
        (THURSDAY, (6.75, 7.5), "Fog: poor visibility"),
        (THURSDAY, (6, 6.5), "Before sunrise (07:03)"),
    ],
)
def test_outdoor_warning(day: date, hours: tuple[float, float], warning: str | None) -> None:
    weather = day_weather(forecast(), day, LISBON_TZ)
    arrive, leave = (round(h * 60) for h in hours)
    assert outdoor_warning(weather, arrive, leave) == warning


def test_showers_from_a_cloudy_step() -> None:
    showers = step(condition="clouds", description="overcast clouds", pop=0.7, precipitation_mm=1)
    noon = datetime(2026, 10, 28, 12, tzinfo=UTC)
    weather = day_weather(
        Forecast((showers,), noon - timedelta(hours=5), noon + timedelta(hours=5)),
        WEDNESDAY,
        LISBON_TZ,
    )
    assert outdoor_warning(weather, 12 * 60, 12 * 60 + 30) == "Showers likely (70%)"


def test_stop_forecast() -> None:
    wednesday = day_weather(forecast(), WEDNESDAY, LISBON_TZ)
    museum = stop_forecast(wednesday, 13 * 60, 14 * 60 + 30, outdoor=False)
    assert museum is not None
    assert (museum.time, museum.description, museum.pop, museum.warning) == (
        "12:00",
        "light rain",
        62,
        None,
    )
    park = stop_forecast(wednesday, 12 * 60, 12 * 60 + 40, outdoor=True)
    assert park is not None and park.warning == "Light rain likely (62%)"
    later = day_weather(forecast(), date(2026, 11, 3), LISBON_TZ)
    assert stop_forecast(later, 13 * 60, 14 * 60, outdoor=True) is None


def test_day_forecast_without_bad_weather_is_headed_by_midday() -> None:
    thursday = day_weather(forecast(), THURSDAY, LISBON_TZ)
    head = day_forecast(thursday, 9 * 60 + 30, 17 * 60 + 30)
    assert head is not None
    assert (head.condition, head.description, head.pop) == ("clear", "clear sky", 0)
    assert [s.time for s in head.slots] == ["09:00", "12:00", "15:00", "18:00"]


def openweather(handler: Any, **kwargs: Any) -> OpenWeatherProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenWeatherProvider(
        API_KEY, url="https://weather.test/forecast", client=client, **kwargs
    )


def test_provider_asks_for_metric_units_and_caches() -> None:
    requests: list[httpx.Request] = []
    now = [1000.0]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=fixture())

    provider = openweather(handler, cache_ttl_s=600, clock=lambda: now[0])
    lisbon = LatLon(38.7438, -9.1582)
    first = asyncio.run(provider.forecast(lisbon))
    assert first is not None and len(first.steps) == 16
    assert asyncio.run(provider.forecast(LatLon(38.7441, -9.1579))) is first  # same place
    now[0] += 601
    assert asyncio.run(provider.forecast(lisbon)) is not first
    assert len(requests) == 2
    params = requests[0].url.params
    assert (params["lat"], params["lon"], params["units"]) == ("38.7438", "-9.1582", "metric")
    assert params["appid"] == API_KEY


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        (httpx.Response(401, json={"cod": 401, "message": "Invalid API key."}), "rejected"),
        (httpx.Response(500, text="oops"), "HTTP 500"),
        (httpx.Response(200, text="<html>"), "JSONDecodeError"),
        (httpx.Response(200, json={"cod": "200", "list": []}), "KeyError"),
        (httpx.ConnectError("connection refused"), "ConnectError"),
    ],
)
def test_failures_mean_no_weather_and_never_log_the_key(
    outcome: httpx.Response | Exception, message: str, caplog: pytest.LogCaptureFixture
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider = openweather(handler)
    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(provider.forecast(LatLon(38.7, -9.1))) is None
        assert asyncio.run(provider.forecast(LatLon(38.7, -9.1))) is None
    assert len(calls) == 2  # failures are not cached
    assert "OpenWeatherMap" in caplog.text and message in caplog.text
    assert API_KEY not in caplog.text


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, type(None)),
        ({"openweather_api_key": ""}, type(None)),
        ({"openweather_api_key": "k"}, OpenWeatherProvider),
    ],
)
def test_factory(overrides: dict[str, Any], expected: type) -> None:
    settings = Settings(_env_file=None, database_url="x", **overrides)
    assert isinstance(create_weather_provider(settings), expected)


def test_city_trip_weather() -> None:
    asked: list[LatLon] = []

    class Fixed:
        async def forecast(self, point: LatLon) -> Forecast | None:
            asked.append(point)
            return forecast()

    lisbon = CITIES["lisbon"]
    trip = asyncio.run(city_trip_weather(Fixed(), lisbon, WEDNESDAY, 3))
    assert trip is not None
    assert [d.date for d in trip.days] == [WEDNESDAY, THURSDAY, date(2026, 10, 30)]
    assert asked == [city_point(lisbon)]
    assert lisbon.bbox.south < asked[0].lat < lisbon.bbox.north
