"""The full pipeline behind POST /plan: select places, optimize the route, save it."""

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Route, RouteStop
from app.llm.service import LLMService
from app.optimizer.distance import DistanceProvider
from app.optimizer.geometry import LatLon
from app.optimizer.planner import DayPlan, StartPoint, Stop, plan_route
from app.schemas.plan import DroppedPlace, PlannedDay, PlannedStop, PlanResponse, StartIn
from app.services.place_selection import select_places


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


def _day_path(day: DayPlan, start: StartIn | None) -> list[LatLon]:
    stops = [LatLon(v.stop.lat, v.stop.lon) for v in day.visits]
    if start is None:
        return stops
    home = LatLon(start.lat, start.lon)
    return [home, *stops] + ([home] if start.round_trip else [])


async def plan_trip(
    *,
    session: AsyncSession,
    llm: LLMService,
    distances: DistanceProvider,
    text: str,
    start: StartIn | None,
    default_city: str,
) -> PlanResponse:
    watch = _Stopwatch()
    selection = await select_places(llm, session, text, default_city=default_city)
    watch.lap("selection")

    places = {p.id: p for p in selection.places}
    stops = [
        Stop(p.id, p.lat, p.lon, p.category, priority=rank)
        for rank, p in enumerate(selection.places)
    ]
    route = await plan_route(
        stops,
        days=selection.trip.days,
        pace=selection.trip.pace,
        provider=distances,
        start=StartPoint(start.lat, start.lon, start.round_trip) if start else None,
    )
    watch.lap("optimization")

    paths = await asyncio.gather(*(distances.geometry(_day_path(d, start)) for d in route.days))
    watch.lap("geometry")

    days = [
        PlannedDay(
            day=day.day,
            stops=[
                PlannedStop(
                    place_id=v.stop.id,
                    name=places[v.stop.id].name,
                    category=v.stop.category,
                    lat=v.stop.lat,
                    lon=v.stop.lon,
                    arrive=_clock(v.arrive_min),
                    leave=_clock(v.leave_min),
                    walk_from_previous_m=round(v.walk_m),
                )
                for v in day.visits
            ],
            distance_m=round(day.distance_m),
            duration_min=day.total_min,
            self_intersections=day.self_intersections,
            geometry=[(p.lon, p.lat) for p in path],
        )
        for day, path in zip(route.days, paths, strict=True)
    ]

    saved = Route(
        city=selection.city,
        request_text=text,
        params={
            "trip": selection.trip.model_dump(mode="json"),
            "start": start.model_dump() if start else None,
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
        dropped=[DroppedPlace(place_id=s.id, name=places[s.id].name) for s in route.dropped],
        warnings=selection.warnings + route.warnings,
        timings_ms=watch.total(),
    )
    saved.result = response.model_dump(mode="json")
    await session.commit()
    return response


async def get_plan(session: AsyncSession, plan_id: int) -> PlanResponse | None:
    saved = await session.get(Route, plan_id)
    if saved is None or saved.result is None:
        return None
    return PlanResponse.model_validate(saved.result)
