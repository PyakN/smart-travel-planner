"""Edit one day of a saved trip as it goes: take stops out, add places, choose the next stop,
plan the rest of the day from where the traveller is. Only the optimizer runs (no LLM), so an
edit is fast and predictable; adding a place found in a search is one such edit.

The result is a draft: a new version of the plan (`parent_id`: the trip's current one) that
the trip does not use until it is saved (PATCH /trips/{id}), so the traveller sees first
what it drops, and why.

- Visited stops stay first, in their planned order.
- The rest of the day is planned from `start` (the traveller's location), from now on when
  the day is under way; else from where the visited stops end, or as the day begins.
- `next` comes first after the visited stops; the others are reordered from it. It is
  visited when the traveller gets there: a place to eat or drink is not held to the hours
  its kind usually keeps (dinner and bars from 20:00), nor to its own opening hours.
- The day keeps its end: back at the hotel on round trips, else wherever its last stop is.
- The day may run until the end of its hours plus REPLAN_GRACE_MIN, whatever the pace.
  Stops drop only beyond that, or when they would be reached closed or dark: least
  important first, and never visited, must-visit, added or next stops.
- Other stops keep their own opening hours (OSM `opening_hours`) on the day's date. Those
  of the places the traveller chose are also checked against their visits: the draft warns
  when one is closed by then, or closes during it.
"""

from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import VENUE_CATEGORIES, VisitHours
from app.db.models import Route
from app.ingest.cities import CITIES, City
from app.optimizer.distance import DistanceProvider
from app.optimizer.planner import (
    MINUTES_PER_DAY,
    REPLAN_GRACE_MIN,
    DayWindow,
    NothingFitsError,
    Origin,
    StartPoint,
    Stop,
    Visit,
    replan_day,
)
from app.optimizer.transit import TransitProvider
from app.osm_hours import Spans, next_change, open_state, read_hours
from app.repositories.candidates import get_candidates
from app.repositories.places import PlaceDetails, place_details
from app.schemas.plan import (
    DroppedStop,
    PlaceRef,
    PlanEdit,
    PlannedDay,
    PlannedStop,
    PlanResponse,
)
from app.schemas.saved_trip import DayEdit
from app.services.place_selection import PlanningError, own_hours
from app.services.plan_editing import latest_day_weather
from app.services.trip_planner import (
    Stopwatch,
    day_segments,
    forecast_of,
    planned_day,
    planned_stop,
    save_plan,
    stays_of,
    transit_source,
    window_of,
)
from app.services.weather_service import WeatherProvider, hhmm, outdoor_conditions

CLOSED_REASON = "It would be closed, or dark, by the time you get there."


def _names(stops: Sequence[PlannedStop]) -> str:
    return ", ".join(s.name for s in stops)


def minute_now(day: PlannedDay, window: DayWindow, city: City, now: datetime) -> int | None:
    """How far into trip day `day` it is `now`, in minutes since its midnight (rounded up);
    None before its hours begin, or for plans without dates. A PlanningError once they end."""
    if day.date is None:
        return None
    local = now.astimezone(city.tz)
    minute = local.hour * 60 + local.minute + (local.second > 0 or local.microsecond > 0)
    elapsed = (local.date() - day.date).days * MINUTES_PER_DAY + minute
    if elapsed < window.start_min:
        return None
    if elapsed >= window.end_min:
        raise PlanningError(f"Day {day.day} is over: its hours ended at {hhmm(window.end_min)}.")
    return elapsed


def opening_warnings(
    visits: Sequence[Visit],
    chosen: Collection[int],
    names: Mapping[int, str],
    details: Mapping[int, PlaceDetails],
    on: date | None,
    city: City,
) -> list[str]:
    """What the opening hours of the places the traveller chose say about their visits on
    day `on`: closed when they get there, or closing before they leave. Nothing for plans
    without dates, or hours that are unknown."""
    if on is None:
        return []
    midnight = datetime.combine(on, time(), city.tz)
    warnings = []
    for visit in visits:
        place = visit.stop
        detail = details.get(place.id)
        if place.id not in chosen or detail is None:
            continue
        hours = read_hours(detail.opening_hours, city, place.lat, place.lon)
        arrive = midnight + timedelta(minutes=visit.arrive_min)
        state = open_state(hours, arrive)
        name = names[place.id]
        if state == "closed":
            warnings.append(f"By its opening hours, {name} is closed at {hhmm(visit.arrive_min)}.")
        elif state == "open":
            closes = next_change(hours, arrive)
            if closes and closes < midnight + timedelta(minutes=visit.leave_min):
                warnings.append(
                    f"By its opening hours, {name} closes at {closes:%H:%M}, before the visit ends."
                )
    return warnings


async def edit_day(
    *,
    session: AsyncSession,
    distances: DistanceProvider,
    plan: PlanResponse,
    visited: Collection[int],
    edit: DayEdit,
    now: datetime,
    transit: TransitProvider | None = None,
    weather: WeatherProvider | None = None,
) -> PlanResponse:
    """A draft of `plan`, a trip's current version, with day `edit.day` changed. `visited`
    are the trip's visited places."""
    watch = Stopwatch()
    saved = await session.get(Route, plan.id)
    city = CITIES.get(plan.city)
    if saved is None or city is None:
        raise PlanningError("This trip's plan can no longer be edited.")
    target = next((d for d in plan.days if d.day == edit.day), None)
    if target is None:
        raise PlanningError(f"Day {edit.day} is not in this plan.")
    day = target.day
    on_day = {s.place_id: s for s in target.stops}
    if any(i not in on_day for i in edit.remove):
        raise PlanningError(f"Only stops of day {day} can be removed.")
    if done := [on_day[i] for i in edit.remove if i in visited]:
        raise PlanningError(f"{_names(done)}: visited places stay on the trip.")

    # The next stop may be a place to add, like the places in `add`.
    adding = list(edit.add)
    if edit.next is not None and edit.next not in on_day and edit.next not in adding:
        adding.append(edit.next)
    places = {c.id: c for c in await get_candidates(session, adding, city=plan.city)}
    planned = {s.place_id: (d.day, s.name) for d in plan.days for s in d.stops}
    for place_id in adding:
        if place_id in planned:
            other, name = planned[place_id]
            raise PlanningError(f"{name} is on day {other} already.")
        if place_id not in places:
            raise PlanningError(f"Place {place_id} is not in {city.name}.")
    if edit.next is not None and edit.next in visited:
        raise PlanningError(f"{on_day[edit.next].name} is visited already.")

    params = saved.params
    ranking = {pid: i for i, pid in enumerate(params.get("ranking", []))}
    stays = stays_of(params)
    # The places the traveller chose in this edit.
    chosen = [*adding, *([edit.next] if edit.next is not None else [])]
    if edit.stay_min is not None:
        stays |= dict.fromkeys(chosen, edit.stay_min)
    removing = set(edit.remove)
    window = window_of(params, day)

    def hours_of(place_id: int, category: str, hours: VisitHours) -> VisitHours:
        if place_id == edit.next and category in VENUE_CATEGORIES:
            return "any"  # visited now, not when places of its kind usually are
        return hours

    def opening_of(
        place_id: int, raw: str | None, lat: float, lon: float
    ) -> dict[date, Spans] | None:
        if place_id == edit.next:
            return None  # visited now: the draft warns if it is closed (opening_warnings)
        return own_hours(raw, city, lat, lon, [window])

    def planned_stop_of(s: PlannedStop, i: int) -> Stop:
        return Stop(
            s.place_id,
            s.lat,
            s.lon,
            s.category,
            priority=ranking.get(s.place_id, len(ranking) + i),
            required=s.must_visit,
            outdoor=s.outdoor,
            hours=hours_of(s.place_id, s.category, s.hours),
            stay_min=stays.get(s.place_id),
            opening_hours=opening_of(s.place_id, s.opening_hours, s.lat, s.lon),
        )

    done_stops = [
        planned_stop_of(s, i) for i, s in enumerate(target.stops) if s.place_id in visited
    ]
    kept = [
        planned_stop_of(s, i)
        for i, s in enumerate(target.stops)
        if s.place_id not in visited and s.place_id not in removing
    ]
    # Added places come last in the ranking, but are never dropped from this edit.
    rank = len(ranking) + len(target.stops)
    added = [
        Stop(
            c.id,
            c.lat,
            c.lon,
            c.category,
            priority=rank + i,
            outdoor=c.outdoor,
            hours=hours_of(c.id, c.category, c.hours),
            stay_min=stays.get(c.id),
            opening_hours=opening_of(c.id, c.opening_hours, c.lat, c.lon),
        )
        for i, c in enumerate(places[p] for p in adding)
    ]
    if not (done_stops or kept or added):
        raise PlanningError(f"Keep at least one stop on day {day}.")

    origin = None
    if edit.start is not None:
        origin = Origin(edit.start.lat, edit.start.lon, minute_now(target, window, city, now))
    aware = await latest_day_weather(weather, plan, day) if plan.weather_aware else None
    today = aware.days[0] if aware else None
    start = plan.start
    try:
        result = await replan_day(
            done_stops,
            [*kept, *added],
            window=window,
            provider=distances,
            start=StartPoint(start.lat, start.lon, start.round_trip) if start else None,
            origin=origin,
            first=edit.next,
            protected=[s.id for s in added],
            modes=plan.modes,
            transit=transit,
            conditions=outdoor_conditions(aware, window.end_min + REPLAN_GRACE_MIN)[0]
            if aware
            else None,
        )
    except NothingFitsError as exc:
        raise PlanningError(
            f"None of these places can be visited in the rest of day {day}, which ends at "
            f"{hhmm(window.end_min)}."
        ) from exc
    watch.lap("optimization")

    current = result.day
    final_ids = [v.stop.id for v in current.visits]
    details = await place_details(session, final_ids)
    names = {s.place_id: s.name for s in target.stops} | {c.id: c.name for c in places.values()}
    notes = {s.place_id: s.note for s in target.stops if s.note}
    edited = planned_day(
        current,
        day,
        [
            planned_stop(v, names[v.stop.id], notes.get(v.stop.id), details.get(v.stop.id), today)
            for v in current.visits
        ],
        await day_segments(current, start, distances),
        on=target.date,
        weather=forecast_of(today, window) if today else target.weather,
    )
    watch.lap("geometry")

    ends = f"The day would end at {hhmm(result.full_end_min)} instead of {hhmm(window.end_min)}."
    dropped = [DroppedStop(place_id=s.id, name=names[s.id], reason=ends) for s in result.over]
    dropped += [
        DroppedStop(place_id=s.id, name=names[s.id], reason=CLOSED_REASON) for s in result.closed
    ]
    warnings = []
    if result.end_min > window.end_min + REPLAN_GRACE_MIN:
        warnings.append(
            f"Day {day} ends at {hhmm(result.end_min)} instead of {hhmm(window.end_min)}: "
            "the places you chose take that long."
        )
    warnings += [
        f"{names[s.id]} closes, or it gets dark, before the visit ends." for s in result.late
    ]
    warnings += opening_warnings(current.visits, chosen, names, details, target.date, city)
    change = PlanEdit(
        day=day,
        kind="edit",
        removed=[PlaceRef(place_id=i, name=on_day[i].name) for i in edit.remove],
        added=[PlaceRef(place_id=c, name=names[c]) for c in adding],
        next=PlaceRef(place_id=edit.next, name=names[edit.next]) if edit.next is not None else None,
        dropped=dropped,
        warnings=warnings,
    )

    days = [edited if d.day == day else d for d in plan.days]
    must_visit = [m for m in plan.must_visit if m.place_id not in removing]
    new_params = {
        **params,
        "must_visit": [m.place_id for m in must_visit],
        # The traveller took these out: replacing stops later does not bring them back.
        "rejected": sorted(set(params.get("rejected", [])) | removing),
        "ranking": [*ranking, *(i for i in final_ids if i not in ranking)],
        "stays": {str(place_id): minutes for place_id, minutes in stays.items()},
        "parent_id": plan.id,
    }
    return await save_plan(
        session,
        city=plan.city,
        text=plan.request_text,
        params=new_params,
        build=lambda new_id: plan.model_copy(
            update={
                "id": new_id,
                "days": days,
                "total_distance_m": sum(d.distance_m for d in days),
                "distance_source": plan.distance_source
                if result.distance_source == plan.distance_source
                else "mixed",
                "transit_source": transit_source(days),
                # A place dropped earlier may be back as an added one.
                "dropped": [d for d in plan.dropped if d.place_id not in final_ids]
                + [PlaceRef(place_id=d.place_id, name=d.name) for d in dropped],
                "timings_ms": watch.total(),
                "must_visit": must_visit,
                "parent_id": plan.id,
                "edit": change,
            }
        ),
    )
