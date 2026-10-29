"""The full pipeline behind POST /plan: select places, optimize the route, save it.

The helpers that turn optimizer output into a saved PlanResponse are shared with plan
editing (app.services.plan_editing).
"""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Route, RouteStop
from app.ingest.cities import CITIES, City
from app.llm.service import LLMService
from app.optimizer.distance import DistanceProvider
from app.optimizer.geometry import LatLon
from app.optimizer.planner import (
    NIGHT_START_MIN,
    DayConditions,
    DayPlan,
    DayWindow,
    Leg,
    NothingFitsError,
    RoutePlan,
    StartPoint,
    Stop,
    Visit,
    plan_route,
)
from app.optimizer.transit import Ride, TransitProvider
from app.repositories.candidates import Candidate
from app.repositories.places import PlaceDetails, place_details
from app.schemas.plan import (
    ALL_MODES,
    Adjustment,
    Attribution,
    DayForecast,
    Departure,
    PlaceRef,
    PlannedDay,
    PlannedStop,
    PlanResponse,
    RouteSegment,
    StartIn,
    StopPhoto,
    TransitRide,
    TravelMode,
)
from app.schemas.trip import Pace
from app.services.day_hours import DEFAULT_HOURS, DailyHours, minute_of, trip_windows
from app.services.place_selection import (
    HoursLookup,
    PlanningError,
    WeatherLookup,
    select_places,
)
from app.services.weather_service import (
    DayWeather,
    TripWeather,
    WeatherProvider,
    city_trip_weather,
    day_forecast,
    hhmm,
    outdoor_conditions,
    stop_forecast,
)

logger = logging.getLogger(__name__)

# A day whose hours run into the evening and go on this long after its last stop ends with a
# free evening: time to eat and drink.
FREE_EVENING_MIN = 60


class Stopwatch:
    def __init__(self) -> None:
        self.started = self.lap_started = time.perf_counter()
        self.laps: dict[str, int] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.laps[name] = round((now - self.lap_started) * 1000)
        self.lap_started = now

    def total(self) -> dict[str, int]:
        return {**self.laps, "total": round((time.perf_counter() - self.started) * 1000)}


def _day_legs(day: DayPlan, start: StartIn | None) -> list[tuple[LatLon, LatLon, Leg]]:
    """Every leg of the day as (from, to, leg), including from/to the start point. A leg
    starts at the stop before, or at its visit's origin on a re-planned day."""
    home = LatLon(start.lat, start.lon) if start is not None else None
    legs = []
    previous = home
    for visit in day.visits:
        here = LatLon(visit.stop.lat, visit.stop.lon)
        origin = LatLon(visit.origin.lat, visit.origin.lon) if visit.origin else previous
        if visit.leg is not None and origin is not None:  # a free start has no leg
            legs.append((origin, here, visit.leg))
        previous = here
    if day.return_leg is not None and home is not None and previous is not None:
        legs.append((previous, home, day.return_leg))
    return legs


def transit_ride(ride: Ride) -> TransitRide:
    return TransitRide(
        vehicle=ride.vehicle,
        line=ride.line,
        headsign=ride.headsign,
        color=ride.color,
        board=ride.board,
        alight=ride.alight,
        stops=ride.stops,
        minutes=round(ride.minutes),
        attributions=[Attribution(text=a.text, url=a.url) for a in ride.attributions],
    )


@dataclass
class _Run:
    mode: TravelMode
    points: list[LatLon]
    # A path that is drawn as is: a transit route's section, or a straight estimated ride.
    # Other walks in a row are routed on the street network together.
    fixed: bool = False
    ride: TransitRide | None = None


async def day_segments(
    day: DayPlan, start: StartIn | None, distances: DistanceProvider
) -> list[RouteSegment]:
    """Walking legs in a row become one street-following path. A ridden leg is drawn as its
    transit route (walks to and from the stops, then each ride along its line), or as a
    straight line when its time is an estimate. Nothing is drawn where the traveller went
    their own way (to the origin of a re-planned day)."""
    runs: list[_Run] = []
    for a, b, leg in _day_legs(day, start):
        if leg.route is not None:
            runs.extend(
                _Run(
                    s.mode, list(s.path), fixed=True, ride=transit_ride(s.ride) if s.ride else None
                )
                for s in leg.route.sections
            )
        elif leg.mode == "transit":
            runs.append(_Run("transit", [a, b], fixed=True))
        elif runs and runs[-1].mode == "walk" and not runs[-1].fixed and runs[-1].points[-1] == a:
            runs[-1].points.append(b)
        else:
            runs.append(_Run("walk", [a, b]))
    if not runs:  # a single stop and no start point
        stop = day.visits[0].stop
        runs = [_Run("walk", [LatLon(stop.lat, stop.lon)])]
    paths = await asyncio.gather(
        *(_straight(run.points) if run.fixed else distances.geometry(run.points) for run in runs)
    )
    return [
        RouteSegment(mode=run.mode, geometry=[(p.lon, p.lat) for p in path], ride=run.ride)
        for run, path in zip(runs, paths, strict=True)
    ]


def transit_source(days: Sequence[PlannedDay]) -> str | None:
    """Where the plan's ride times come from: "here", "estimate" or "mixed"."""
    sources = {
        "here" if segment.ride else "estimate"
        for day in days
        for segment in day.segments
        if segment.mode == "transit"
    }
    if len(sources) > 1:
        return "mixed"
    return sources.pop() if sources else None


async def _straight(points: list[LatLon]) -> list[LatLon]:
    return points


def _photo(details: PlaceDetails | None) -> StopPhoto | None:
    if details is None or details.image_url is None:
        return None
    return StopPhoto(
        url=details.image_url, page_url=details.image_page_url, credit=details.image_credit
    )


def planned_stop(
    visit: Visit,
    name: str,
    note: str | None,
    details: PlaceDetails | None,
    weather: DayWeather | None = None,
) -> PlannedStop:
    leg = visit.leg
    stop = visit.stop
    forecast = (
        stop_forecast(
            weather, visit.arrive_min, visit.leave_min, stop.outdoor, stop.hours == "daylight"
        )
        if weather
        else None
    )
    return PlannedStop(
        place_id=visit.stop.id,
        name=name,
        category=visit.stop.category,
        lat=visit.stop.lat,
        lon=visit.stop.lon,
        arrive=hhmm(visit.arrive_min),
        leave=hhmm(visit.leave_min),
        travel_mode=leg.mode if leg else None,
        travel_min=round(leg.minutes) if leg else 0,
        distance_from_previous_m=round(leg.distance_m) if leg else 0,
        rides=[transit_ride(r) for r in leg.route.rides] if leg and leg.route else [],
        must_visit=visit.stop.required,
        note=note,
        description=details.description if details else None,
        photo=_photo(details),
        opening_hours=details.opening_hours if details else None,
        website=details.website if details else None,
        outdoor=stop.outdoor,
        weather=forecast,
        hours=stop.hours,
        wait_min=visit.wait_min,
        departure=Departure(
            lat=visit.origin.lat, lon=visit.origin.lon, time=hhmm(visit.origin.minute)
        )
        if visit.origin and visit.origin.minute is not None
        else None,
    )


def free_evening(day: DayPlan) -> str | None:
    """When the day's free evening begins (the last stop's leaving time), if it has one."""
    if not day.visits:
        return None
    leave, end = day.visits[-1].leave_min, day.window.end_min
    if end <= NIGHT_START_MIN or end - leave < FREE_EVENING_MIN:
        return None
    return hhmm(leave)


def planned_day(
    day: DayPlan,
    number: int,
    stops: list[PlannedStop],
    segments: list[RouteSegment],
    *,
    on: date | None = None,
    weather: DayForecast | None = None,
) -> PlannedDay:
    window = day.window
    return PlannedDay(
        day=number,
        stops=stops,
        distance_m=round(day.distance_m),
        walking_m=round(day.walking_m),
        transit_legs=day.transit_legs,
        duration_min=day.total_min,
        self_intersections=day.self_intersections,
        segments=segments,
        date=on,
        weather=weather,
        start=hhmm(window.start_min),
        end=hhmm(window.end_min),
        sunrise=hhmm(window.sunrise_min) if window.sunrise_min is not None else None,
        sunset=hhmm(window.sunset_min) if window.sunset_min is not None else None,
        free_from=free_evening(day),
    )


def window_params(window: DayWindow) -> list[int | None]:
    """A day's hours as saved with the plan: [start, end, sunrise, sunset]."""
    return [window.start_min, window.end_min, window.sunrise_min, window.sunset_min]


def window_of(params: dict[str, Any], day: int) -> DayWindow:
    """The hours of day `day` (1 is the first) of a saved plan; plans saved before days had
    their own hours get the default ones."""
    saved = params.get("windows") or []
    return DayWindow(*saved[day - 1]) if day <= len(saved) else DayWindow()


def stays_of(params: dict[str, Any]) -> dict[int, int]:
    """Minutes the traveller chose to stay at places of a saved plan, by place id."""
    return {int(place_id): minutes for place_id, minutes in params.get("stays", {}).items()}


async def optimize(
    stops: Sequence[Stop],
    *,
    days: int,
    pace: Pace,
    provider: DistanceProvider,
    start: StartPoint | None,
    modes: Sequence[TravelMode],
    transit: TransitProvider | None,
    conditions: Sequence[DayConditions] | None,
    windows: Sequence[DayWindow],
) -> RoutePlan:
    """plan_route; hours that no stop fits are a PlanningError."""
    try:
        return await plan_route(
            stops,
            days=days,
            pace=pace,
            provider=provider,
            start=start,
            modes=modes,
            transit=transit,
            conditions=conditions,
            windows=windows,
        )
    except NothingFitsError as exc:
        raise PlanningError(
            "None of these places can be visited in the hours you chose: sights close and "
            "bars open at 20:00, and viewpoints need daylight."
        ) from exc


def swap(removed: Candidate, added: Candidate, reason: str) -> Adjustment:
    return Adjustment(
        removed=PlaceRef(place_id=removed.id, name=removed.name),
        added=PlaceRef(place_id=added.id, name=added.name),
        reason=reason,
    )


def first_day(city: City, requested: date | None) -> date:
    """The trip's first day: the requested one, or tomorrow in the city."""
    return requested or city.today() + timedelta(days=1)


def weather_lookup(provider: WeatherProvider, start_date: date | None) -> WeatherLookup:
    async def lookup(city: City, days: int) -> TripWeather | None:
        return await city_trip_weather(provider, city, first_day(city, start_date), days)

    return lookup


def hours_lookup(hours: DailyHours, start_date: date | None, now: datetime | None) -> HoursLookup:
    def lookup(city: City, days: int) -> list[DayWindow]:
        moment = now or datetime.now(city.tz)
        return trip_windows(hours, city, first_day(city, start_date), days, moment)

    return lookup


def late_start_warnings(hours: DailyHours, windows: Sequence[DayWindow]) -> list[str]:
    """A trip that starts today, later than asked: now is too late for that."""
    asked = minute_of(hours.first_start or hours.start)
    if not windows or windows[0].start_min <= asked:
        return []
    return [f"Day 1 starts at {hhmm(windows[0].start_min)}: it is past {hhmm(asked)} already."]


def day_weather_of(weather: TripWeather | None, day: int) -> DayWeather | None:
    """Trip day `day` (1 is the first) of the trip's weather, if any."""
    return weather.days[day - 1] if weather and day <= len(weather.days) else None


def forecast_of(weather: DayWeather | None, window: DayWindow) -> DayForecast | None:
    """The forecast of a day's hours, in the 3-hour steps they overlap."""
    return day_forecast(weather, window.start_min, window.end_min) if weather else None


def latest_end(windows: Sequence[DayWindow]) -> int:
    return max(w.end_min for w in windows)


def weather_warnings(weather: TripWeather | None, weather_aware: bool) -> list[str]:
    """What a weather-aware plan could not know. Stops that meet bad weather say so
    themselves (`PlannedStop.weather.warning`)."""
    if not weather_aware:
        return []
    if weather is None:
        return ["No weather forecast is available, so the plan ignores it."]
    unknown = [str(i) for i, day in enumerate(weather.days, start=1) if not day.has_forecast]
    if not unknown:
        return []
    listed = ", ".join(unknown)
    return [f"No forecast yet for day {listed}; outdoor stops there only avoid the dark."]


async def save_plan(
    session: AsyncSession,
    *,
    city: str,
    text: str,
    params: dict[str, Any],
    build: Callable[[int], PlanResponse],
) -> PlanResponse:
    """Store a new plan: `build` makes the response once the plan id is known."""
    saved = Route(city=city, request_text=text, params=params)
    session.add(saved)
    await session.flush()  # assigns saved.id
    response = build(saved.id)
    session.add_all(
        RouteStop(route_id=saved.id, place_id=stop.place_id, day=day.day, position=position)
        for day in response.days
        for position, stop in enumerate(day.stops, start=1)
    )
    saved.total_distance_m = response.total_distance_m
    saved.result = response.model_dump(mode="json")
    await session.commit()
    return response


async def plan_trip(
    *,
    session: AsyncSession,
    llm: LLMService,
    distances: DistanceProvider,
    text: str,
    start: StartIn | None,
    default_city: str,
    must_visit: Sequence[int] = (),
    modes: Sequence[TravelMode] = ALL_MODES,
    transit: TransitProvider | None = None,
    weather: WeatherProvider | None = None,
    start_date: date | None = None,
    weather_aware: bool = False,
    hours: DailyHours = DEFAULT_HOURS,
    now: datetime | None = None,
    chosen_city: str | None = None,
) -> PlanResponse:
    """`weather_aware` plans with the `weather` forecast and gives every day and stop its
    forecast; other plans never ask for it. `hours` are the days' hours; a first day that
    is today starts at `now` (the current time) or later. `chosen_city` is the trip's city (see
    select_places)."""
    watch = Stopwatch()
    selection = await select_places(
        llm,
        session,
        text,
        default_city=default_city,
        must_visit=must_visit,
        start=LatLon(start.lat, start.lon) if start else None,
        modes=modes,
        weather=weather_lookup(weather, start_date) if weather and weather_aware else None,
        weather_aware=weather_aware,
        hours=hours_lookup(hours, start_date, now),
        chosen_city=chosen_city,
    )
    watch.lap("selection")
    windows = selection.windows
    forecast = selection.weather
    first = forecast.days[0].date if forecast else first_day(CITIES[selection.city], start_date)

    places = {p.id: p for p in selection.places}
    required = {p.id for p in selection.must_visit}
    stops = [
        Stop(
            p.id,
            p.lat,
            p.lon,
            p.category,
            priority=rank,
            required=p.id in required,
            outdoor=p.outdoor,
            hours=p.hours,
        )
        for rank, p in enumerate(selection.places)
    ]
    route = await optimize(
        stops,
        windows=windows,
        days=selection.trip.days,
        pace=selection.trip.pace,
        provider=distances,
        start=StartPoint(start.lat, start.lon, start.round_trip) if start else None,
        modes=modes,
        transit=transit,
        conditions=outdoor_conditions(forecast, latest_end(windows)) if forecast else None,
    )
    watch.lap("optimization")

    segments = await asyncio.gather(*(day_segments(d, start, distances) for d in route.days))
    watch.lap("geometry")
    details = await place_details(session, [v.stop.id for d in route.days for v in d.visits])

    days = []
    for day, segments_of_day in zip(route.days, segments, strict=True):
        today = day_weather_of(forecast, day.day)
        stops_of_day = [
            planned_stop(
                v,
                places[v.stop.id].name,
                selection.notes.get(v.stop.id),
                details.get(v.stop.id),
                today,
            )
            for v in day.visits
        ]
        days.append(
            planned_day(
                day,
                day.day,
                stops_of_day,
                segments_of_day,
                on=first + timedelta(days=day.day - 1),
                weather=forecast_of(today, day.window),
            )
        )
    weather_reason = "The forecast leaves too few dry daylight hours for it outdoors."
    swaps = [swap(outdoor, indoor, weather_reason) for outdoor, indoor in selection.weather_swaps]
    hours_swaps = [swap(old, new, reason) for old, new, reason in selection.hours_swaps]
    params = {
        "trip": selection.trip.model_dump(mode="json"),
        "start": start.model_dump() if start else None,
        "must_visit": [p.id for p in selection.must_visit],
        "modes": list(modes),
        # Selection order, most important first: decides what is trimmed first in edits.
        "ranking": [p.id for p in selection.places],
        "start_date": first.isoformat(),
        "weather_aware": weather_aware,
        **hours.as_params(),
        "windows": [window_params(w) for w in windows],
    }
    return await save_plan(
        session,
        city=selection.city,
        text=text,
        params=params,
        build=lambda plan_id: PlanResponse(
            id=plan_id,
            request_text=text,
            city=selection.city,
            trip=selection.trip,
            rationale=selection.rationale,
            days=days,
            total_distance_m=round(route.total_distance_m),
            distance_source=route.distance_source,
            transit_source=transit_source(days),
            strategy=route.strategy,
            dropped=[PlaceRef(place_id=s.id, name=places[s.id].name) for s in route.dropped],
            warnings=late_start_warnings(hours, windows)
            + selection.warnings
            + route.warnings
            + weather_warnings(forecast, weather_aware),
            timings_ms=watch.total(),
            modes=list(modes),
            must_visit=[PlaceRef(place_id=p.id, name=p.name) for p in selection.must_visit],
            start=start,
            start_date=first,
            weather_aware=weather_aware,
            weather_swaps=swaps,
            hours_swaps=hours_swaps,
            **hours.as_params(),
        ),
    )


async def get_plan(session: AsyncSession, plan_id: int) -> PlanResponse | None:
    saved = await session.get(Route, plan_id)
    if saved is None or saved.result is None:
        return None
    try:
        return PlanResponse.model_validate(saved.result)
    except ValidationError:
        # Saved by an older version with a different response shape.
        logger.warning("plan %d has an outdated format", plan_id)
        return None
