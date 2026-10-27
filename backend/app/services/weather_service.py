"""Weather for a trip's days: OpenWeatherMap's 5 day / 3 hour forecast.

Weather-aware plans keep outdoor stops (viewpoints, parks, statues) out of hours with rain,
snow, fog, poor visibility or darkness, and every plan shows the forecast for its days and
stops.

The forecast reaches five days ahead in three-hour steps; a moment takes the step whose
three hours it falls in. Sunrise and sunset come with it for the current day. Later days
reuse them shifted by whole days (they move a minute or two a day), so darkness is known on
every trip day, also past the forecast's reach. Times are the city's local wall clock, in
minutes since midnight like the optimizer's schedule.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import inf
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings
from app.http_logging import hide_api_keys
from app.ingest.cities import City
from app.optimizer.geometry import LatLon

logger = logging.getLogger(__name__)
hide_api_keys()

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"
MINUTES_PER_DAY = 24 * 60
STEP_MIN = 180
# Below the first visibility there is nothing to see from a viewpoint; below the second,
# views are dull.
FOG_VISIBILITY_M = 1000
HAZE_VISIBILITY_M = 4000
# From this badness on, a moment counts as bad for outdoor sights.
BAD_WEATHER = 0.5
CACHE_TTL_S = 30 * 60

Condition = Literal["clear", "clouds", "fog", "drizzle", "rain", "snow", "thunderstorm"]
# OpenWeatherMap's condition groups by the code's first digit; 7xx is mist, haze, fog, dust.
_GROUPS: dict[int, Condition] = {2: "thunderstorm", 3: "drizzle", 5: "rain", 6: "snow", 7: "fog"}
WET: frozenset[Condition] = frozenset({"thunderstorm", "drizzle", "rain", "snow"})


def condition(weather_id: int) -> Condition:
    if weather_id == 800:
        return "clear"
    return _GROUPS.get(weather_id // 100, "clouds")


@dataclass(frozen=True)
class WeatherStep:
    """The forecast for the three hours around `time`."""

    time: datetime  # UTC
    temp_c: float
    condition: Condition
    description: str  # "light rain"
    icon: str  # OpenWeatherMap icon code, "10d"
    pop: float  # chance of rain or snow, 0..1
    precipitation_mm: float  # rain and snow over the three hours
    visibility_m: int | None

    @property
    def outdoor_badness(self) -> float:
        """How unfit the weather is for outdoor sights, from 0 (fine) to 1 (stay inside).

        Rain, drizzle, snow and thunderstorms count with their chance; fog and haze by how
        little they leave to see.
        """
        wet = self.pop if self.condition in WET or self.precipitation_mm > 0 else 0.0
        visibility = inf if self.visibility_m is None else self.visibility_m
        if visibility < FOG_VISIBILITY_M:
            murky = 1.0
        elif self.condition == "fog" or visibility < HAZE_VISIBILITY_M:
            murky = 0.5
        else:
            murky = 0.0
        return max(wet, murky)


@dataclass(frozen=True)
class Forecast:
    steps: tuple[WeatherStep, ...]  # in time order
    sunrise: datetime  # the current day's, UTC
    sunset: datetime


def _utc(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, UTC)


def _step(raw: dict[str, Any]) -> WeatherStep:
    weather = raw["weather"][0]
    visibility = raw.get("visibility")
    return WeatherStep(
        time=_utc(raw["dt"]),
        temp_c=float(raw["main"]["temp"]),
        condition=condition(int(weather["id"])),
        description=str(weather.get("description", "")),
        icon=str(weather.get("icon", "")),
        pop=float(raw.get("pop", 0.0)),
        precipitation_mm=sum(float(raw.get(kind, {}).get("3h", 0.0)) for kind in ("rain", "snow")),
        visibility_m=int(visibility) if visibility is not None else None,
    )


def parse_forecast(body: dict[str, Any]) -> Forecast:
    city = body["city"]
    steps = sorted(map(_step, body["list"]), key=lambda s: s.time)
    return Forecast(tuple(steps), _utc(city["sunrise"]), _utc(city["sunset"]))


@dataclass(frozen=True)
class DayWeather:
    """One trip day, in the city's local minutes since midnight."""

    date: date
    sunrise_min: int
    sunset_min: int
    # Forecast steps around the day, by local minute (negative for the evening before).
    steps: tuple[tuple[int, WeatherStep], ...]

    def at(self, minute: float) -> WeatherStep | None:
        """The step whose three hours `minute` falls in; None past the forecast's reach."""
        for start, step in self.steps:
            if start - STEP_MIN / 2 <= minute < start + STEP_MIN / 2:
                return step
        return None

    @property
    def has_forecast(self) -> bool:
        return any(0 <= minute < MINUTES_PER_DAY for minute, _ in self.steps)

    def is_dark(self, minute: float) -> bool:
        return not self.sunrise_min <= minute < self.sunset_min

    def outdoor_badness(self, minute: float) -> float:
        """Bad weather or darkness at `minute`: 0 (fine for outdoor sights) to 1."""
        if self.is_dark(minute):
            return 1.0
        step = self.at(minute)
        return step.outdoor_badness if step else 0.0

    def minute_badness(self) -> list[float]:
        return [self.outdoor_badness(minute) for minute in range(MINUTES_PER_DAY)]


def day_weather(forecast: Forecast, day: date, tz: ZoneInfo) -> DayWeather:
    def minute(moment: datetime) -> int:
        local = moment.astimezone(tz)
        return (local.date() - day).days * MINUTES_PER_DAY + local.hour * 60 + local.minute

    # Shifted in UTC, so the local clock follows daylight saving changes.
    shift = timedelta(days=(day - forecast.sunrise.astimezone(tz).date()).days)
    steps = tuple(
        (m, step)
        for step in forecast.steps
        if -STEP_MIN <= (m := minute(step.time)) < MINUTES_PER_DAY + STEP_MIN
    )
    return DayWeather(day, minute(forecast.sunrise + shift), minute(forecast.sunset + shift), steps)


@dataclass(frozen=True)
class TripWeather:
    days: tuple[DayWeather, ...]  # the trip's days in order

    def outdoor_share(self, start_min: int, end_min: int) -> float:
        """Share of the sightseeing hours, `start_min` to `end_min` every day, that suit
        outdoor sights: dry, clear enough and light."""
        fine = [
            day.outdoor_badness(minute) < BAD_WEATHER
            for day in self.days
            for minute in range(start_min, end_min)
        ]
        return sum(fine) / len(fine) if fine else 1.0


def trip_weather(forecast: Forecast, start: date, days: int, tz: ZoneInfo) -> TripWeather:
    return TripWeather(
        tuple(day_weather(forecast, start + timedelta(days=i), tz) for i in range(days))
    )


class WeatherProvider(Protocol):
    async def forecast(self, point: LatLon) -> Forecast | None:
        """The forecast at `point`; None when it is unavailable."""
        ...


class OpenWeatherProvider:
    """OpenWeatherMap's 5 day / 3 hour forecast; each place's answer is reused for a while.

    Failures are not cached: the plan goes without weather and the next one asks again.
    """

    def __init__(
        self,
        api_key: str,
        *,
        url: str = OPENWEATHER_URL,
        timeout_s: float = 5.0,
        cache_ttl_s: float = CACHE_TTL_S,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self.url = url
        self.timeout_s = timeout_s
        self.cache_ttl_s = cache_ttl_s
        self._client = client
        self._clock = clock
        self._cache: dict[tuple[float, float], tuple[float, Forecast]] = {}

    async def forecast(self, point: LatLon) -> Forecast | None:
        key = (round(point.lat, 2), round(point.lon, 2))
        if (cached := self._cache.get(key)) and self._clock() - cached[0] < self.cache_ttl_s:
            return cached[1]
        params = {
            "lat": f"{point.lat:.4f}",
            "lon": f"{point.lon:.4f}",
            "units": "metric",
            "appid": self._api_key,
        }
        try:
            if self._client is not None:
                response = await self._client.get(self.url, params=params, timeout=self.timeout_s)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self.url, params=params, timeout=self.timeout_s)
            response.raise_for_status()
            forecast = parse_forecast(response.json())
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                # New keys take a while to activate; until then OpenWeatherMap answers 401.
                logger.error("OpenWeatherMap rejected the API key (HTTP 401); no weather")
            else:
                logger.warning("OpenWeatherMap failed (HTTP %d); no weather", status)
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            # Never the exception text: httpx puts the request URL, API key included, in it.
            logger.warning("OpenWeatherMap failed (%s); no weather", type(exc).__name__)
            return None
        self._cache[key] = (self._clock(), forecast)
        return forecast


def create_weather_provider(settings: Settings) -> WeatherProvider | None:
    """OpenWeatherMap forecasts; None (plans without weather) without a key."""
    if not settings.openweather_api_key:
        return None
    return OpenWeatherProvider(
        settings.openweather_api_key.get_secret_value(),
        url=settings.openweather_url,
        timeout_s=settings.openweather_timeout_s,
    )


def city_point(city: City) -> LatLon:
    box = city.bbox
    return LatLon((box.south + box.north) / 2, (box.west + box.east) / 2)


async def city_trip_weather(
    provider: WeatherProvider, city: City, start: date, days: int
) -> TripWeather | None:
    """The weather of a trip's days in `city`; None when there is no forecast."""
    forecast = await provider.forecast(city_point(city))
    return trip_weather(forecast, start, days, city.tz) if forecast else None
