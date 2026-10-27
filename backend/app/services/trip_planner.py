"""The full pipeline behind POST /plan: select places, optimize the route, save it."""

import asyncio
import logging
import time
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Route, RouteStop
from app.llm.service import LLMService
from app.optimizer.distance import DistanceProvider
from app.optimizer.geometry import LatLon
from app.optimizer.planner import DayPlan, Leg, StartPoint, Stop, Visit, plan_route
from app.repositories.places import PlaceDetails, place_details
from app.schemas.plan import (
    ALL_MODES,
    PlaceRef,
    PlannedDay,
    PlannedStop,
    PlanResponse,
    RouteSegment,
    StartIn,
    StopPhoto,
    TravelMode,
)
from app.services.place_selection import select_places

logger = logging.getLogger(__name__)


def _clock(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class _Stopwatch:
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
    """Every leg of the day as (from, to, leg), including from/to the start point."""
    points = [LatLon(v.stop.lat, v.stop.lon) for v in day.visits]
    legs = [v.leg for v in day.visits]
    if start is not None:
        home = LatLon(start.lat, start.lon)
        points.insert(0, home)
        if day.return_leg is not None:
            points.append(home)
            legs.append(day.return_leg)
    else:
        legs = legs[1:]  # a free start has no leg into the first stop
    return [
        (a, b, leg)
        for a, b, leg in zip(points[:-1], points[1:], legs, strict=True)
        if leg is not None
    ]


async def _segments(
    day: DayPlan, start: StartIn | None, distances: DistanceProvider
) -> list[RouteSegment]:
    """Consecutive walking legs become one street-following path; transit legs stay straight."""
    runs: list[tuple[TravelMode, list[LatLon]]] = []
    for a, b, leg in _day_legs(day, start):
        if leg.mode == "walk" and runs and runs[-1][0] == "walk":
            runs[-1][1].append(b)
        else:
            runs.append((leg.mode, [a, b]))
    if not runs:  # a single stop and no start point
        stop = day.visits[0].stop
        runs = [("walk", [LatLon(stop.lat, stop.lon)])]
    paths = await asyncio.gather(
        *(
            distances.geometry(points) if mode == "walk" else _straight(points)
            for mode, points in runs
        )
    )
    return [
        RouteSegment(mode=mode, geometry=[(p.lon, p.lat) for p in path])
        for (mode, _), path in zip(runs, paths, strict=True)
    ]


async def _straight(points: list[LatLon]) -> list[LatLon]:
    return points


def _photo(details: PlaceDetails | None) -> StopPhoto | None:
    if details is None or details.image_url is None:
        return None
    return StopPhoto(
        url=details.image_url, page_url=details.image_page_url, credit=details.image_credit
    )


def _planned_stop(
    visit: Visit, name: str, note: str | None, details: PlaceDetails | None
) -> PlannedStop:
    leg = visit.leg
    return PlannedStop(
        place_id=visit.stop.id,
        name=name,
        category=visit.stop.category,
        lat=visit.stop.lat,
        lon=visit.stop.lon,
        arrive=_clock(visit.arrive_min),
        leave=_clock(visit.leave_min),
        travel_mode=leg.mode if leg else None,
        travel_min=round(leg.minutes) if leg else 0,
        distance_from_previous_m=round(leg.distance_m) if leg else 0,
        must_visit=visit.stop.required,
        note=note,
        description=details.description if details else None,
        photo=_photo(details),
        opening_hours=details.opening_hours if details else None,
        website=details.website if details else None,
    )


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
) -> PlanResponse:
    watch = _Stopwatch()
    selection = await select_places(
        llm,
        session,
        text,
        default_city=default_city,
        must_visit=must_visit,
        start=LatLon(start.lat, start.lon) if start else None,
        modes=modes,
    )
    watch.lap("selection")

    places = {p.id: p for p in selection.places}
    required = {p.id for p in selection.must_visit}
    stops = [
        Stop(p.id, p.lat, p.lon, p.category, priority=rank, required=p.id in required)
        for rank, p in enumerate(selection.places)
    ]
    route = await plan_route(
        stops,
        days=selection.trip.days,
        pace=selection.trip.pace,
        provider=distances,
        start=StartPoint(start.lat, start.lon, start.round_trip) if start else None,
        modes=modes,
    )
    watch.lap("optimization")

    segments = await asyncio.gather(*(_segments(d, start, distances) for d in route.days))
    watch.lap("geometry")
    details = await place_details(session, [v.stop.id for d in route.days for v in d.visits])

    days = [
        PlannedDay(
            day=day.day,
            stops=[
                _planned_stop(
                    v,
                    places[v.stop.id].name,
                    selection.notes.get(v.stop.id),
                    details.get(v.stop.id),
                )
                for v in day.visits
            ],
            distance_m=round(day.distance_m),
            walking_m=round(day.walking_m),
            transit_legs=day.transit_legs,
            duration_min=day.total_min,
            self_intersections=day.self_intersections,
            segments=day_segments,
        )
        for day, day_segments in zip(route.days, segments, strict=True)
    ]

    saved = Route(
        city=selection.city,
        request_text=text,
        params={
            "trip": selection.trip.model_dump(mode="json"),
            "start": start.model_dump() if start else None,
            "must_visit": [p.id for p in selection.must_visit],
            "modes": list(modes),
        },
        total_distance_m=route.total_distance_m,
    )
    session.add(saved)
    await session.flush()  # assigns saved.id
    session.add_all(
        RouteStop(route_id=saved.id, place_id=stop.place_id, day=day.day, position=position)
        for day in days
        for position, stop in enumerate(day.stops, start=1)
    )

    response = PlanResponse(
        id=saved.id,
        request_text=text,
        city=selection.city,
        trip=selection.trip,
        rationale=selection.rationale,
        days=days,
        total_distance_m=round(route.total_distance_m),
        distance_source=route.distance_source,
        strategy=route.strategy,
        dropped=[PlaceRef(place_id=s.id, name=places[s.id].name) for s in route.dropped],
        warnings=selection.warnings + route.warnings,
        timings_ms=watch.total(),
        modes=list(modes),
        must_visit=[PlaceRef(place_id=p.id, name=p.name) for p in selection.must_visit],
    )
    saved.result = response.model_dump(mode="json")
    await session.commit()
    return response


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
