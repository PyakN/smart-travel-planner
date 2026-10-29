"""Re-planning a day as it goes: visited stops first, the rest from where the traveller is."""

import asyncio
from collections.abc import Collection, Sequence

import pytest

from app.catalog import VisitHours
from app.geo import haversine_m
from app.optimizer.distance import DETOUR_FACTOR, HaversineProvider
from app.optimizer.geometry import LatLon
from app.optimizer.planner import (
    REPLAN_GRACE_MIN,
    WALKING_M_PER_MIN,
    DayReplan,
    DayWindow,
    NothingFitsError,
    Origin,
    StartPoint,
    Stop,
    plan_route,
    replan_day,
)

H = 60
DAY = DayWindow(9 * H + 30, 21 * H + 30, sunrise_min=7 * H, sunset_min=18 * H)
HOTEL = StartPoint(38.7100, -9.1400, round_trip=True)
STEP = 0.002  # ~220 m: about 4 minutes on foot


def stop(
    i: int,
    north: float = 0.0,
    east: float = 0.0,
    *,
    stay: int | None = 30,
    category: str = "landmark",
    hours: VisitHours = "any",
    required: bool = False,
) -> Stop:
    """Stop 100 + i, `north` and `east` steps from the hotel; priority i (0 matters most)."""
    lat, lon = HOTEL.lat + north * STEP, HOTEL.lon + east * STEP
    return Stop(
        100 + i, lat, lon, category, priority=i, required=required, hours=hours, stay_min=stay
    )


def replan(
    done: Sequence[Stop],
    stops: Sequence[Stop],
    *,
    start: StartPoint | None = HOTEL,
    origin: Origin | None = None,
    first: int | None = None,
    protected: Collection[int] = (),
    window: DayWindow = DAY,
) -> DayReplan:
    return asyncio.run(
        replan_day(
            done,
            stops,
            window=window,
            provider=HaversineProvider(),
            start=start,
            origin=origin,
            first=first,
            protected=protected,
            modes=("walk",),
        )
    )


def ids(result: DayReplan) -> list[int]:
    return [v.stop.id for v in result.day.visits]


def walk_min(a: LatLon | Stop | StartPoint | Origin, b: Stop | StartPoint) -> float:
    return DETOUR_FACTOR * haversine_m(a.lat, a.lon, b.lat, b.lon) / WALKING_M_PER_MIN


def test_visited_stops_stay_first_and_the_rest_follows_from_the_last() -> None:
    # The traveller went east first; the stops left are back west, nearest first.
    done = [stop(0, east=4), stop(1, east=2)]
    rest = [stop(2, east=-1), stop(3, east=1), stop(4, east=-3)]
    hotel = StartPoint(HOTEL.lat, HOTEL.lon)  # not a round trip
    result = replan(done, rest, start=hotel)
    assert ids(result) == [100, 101, 103, 102, 104]

    first, second, after = result.day.visits[:3]
    assert first.arrive_min == pytest.approx(DAY.start_min + walk_min(hotel, done[0]), abs=1)
    assert after.arrive_min == pytest.approx(second.leave_min + walk_min(done[1], rest[1]), abs=1)
    assert after.origin is None  # it sets off from the stop before
    assert result.day.return_leg is None
    assert result.over == result.closed == result.late == []


def test_rest_of_the_day_from_the_travellers_location_now() -> None:
    here = Origin(HOTEL.lat + 6 * STEP, HOTEL.lon, minute=14 * H + 5)
    done = [stop(0, east=3)]
    # Ending at the hotel: the far stop first, then the one on the way back.
    rest = [stop(1, north=3), stop(2, north=7)]
    result = replan(done, rest, origin=here)
    assert ids(result) == [100, 102, 101]

    resumed = result.day.visits[1]
    assert resumed.origin == here
    assert resumed.leg is not None
    assert resumed.leg.distance_m == pytest.approx(
        DETOUR_FACTOR * haversine_m(here.lat, here.lon, rest[1].lat, rest[1].lon)
    )
    assert resumed.arrive_min == round(here.minute + walk_min(here, rest[1]))  # type: ignore[operator]
    assert result.end_min == pytest.approx(
        result.day.visits[-1].leave_min + walk_min(rest[0], HOTEL), abs=1
    )


def test_an_origin_without_a_time_begins_where_the_visited_stops_end() -> None:
    here = Origin(HOTEL.lat, HOTEL.lon + 5 * STEP)
    done = [stop(0, east=1)]
    result = replan(done, [stop(1, east=6)], origin=here)
    visited, resumed = result.day.visits
    assert resumed.origin == Origin(here.lat, here.lon, minute=visited.leave_min)
    assert resumed.arrive_min == round(visited.leave_min + walk_min(here, stop(1, east=6)))


def test_the_next_stop_comes_first_then_the_rest_is_reordered_from_it() -> None:
    rest = [stop(0, east=1), stop(1, east=2), stop(2, east=6), stop(3, east=4)]
    result = replan([], rest, first=102)
    assert ids(result) == [102, 103, 101, 100]  # out to it, then back towards the hotel
    assert result.day.visits[0].leg is not None


def test_the_next_stop_stays_first_when_the_hours_reorder_the_day() -> None:
    # From 17:00 a viewpoint fits before the 18:00 sunset, but not after the museum the
    # traveller wants to go to first: the viewpoint is dropped, the museum stays first.
    origin = Origin(HOTEL.lat, HOTEL.lon, minute=17 * H)
    museum = stop(0, east=2, stay=None, category="museum", hours="day")
    viewpoint = stop(1, east=1, stay=None, category="viewpoint", hours="daylight")
    result = replan([], [museum, viewpoint], origin=origin, first=museum.id)
    assert ids(result) == [museum.id]
    assert result.closed == [viewpoint]


def test_the_day_may_run_to_its_end_whatever_the_pace() -> None:
    # Nine hour-long stops are over 9 h: more than a moderate pace's 8 h, so a new plan
    # drops some, but they end before 21:30, so the re-planned day keeps them all.
    stops = [stop(i, east=i % 3, north=i // 3, stay=60) for i in range(9)]
    provider = HaversineProvider()
    new = asyncio.run(
        plan_route(stops, days=1, pace="moderate", provider=provider, start=HOTEL, windows=[DAY])
    )
    assert new.dropped

    result = replan([], stops)
    assert sorted(ids(result)) == [s.id for s in stops]
    assert result.over == []
    assert DAY.start_min + result.day.total_min == result.end_min <= DAY.end_min


def test_stops_drop_only_past_the_end_least_important_first() -> None:
    stops = [stop(i, east=i % 4, north=i // 4, stay=60) for i in range(13)]
    result = replan([], stops)
    assert result.over == stops[-len(result.over) :]  # the least important ones
    assert result.full_end_min > DAY.end_min + REPLAN_GRACE_MIN
    assert result.end_min <= DAY.end_min + REPLAN_GRACE_MIN
    # Within the grace: the day may end a little after 21:30.
    assert result.end_min > DAY.end_min - 60


def test_must_visit_protected_and_next_stops_are_never_dropped() -> None:
    stops = [stop(i, east=i % 4, north=i // 4, stay=60) for i in range(13)]
    stops[11] = stop(11, east=3, north=2, stay=60, required=True)
    least = stops[12].id
    result = replan([], stops, protected=[least], first=stops[10].id)
    kept = set(ids(result))
    assert {stops[10].id, stops[11].id, least} <= kept
    assert result.over and all(s.priority < 10 for s in result.over)


def test_protected_stops_stay_even_when_the_day_runs_long() -> None:
    stops = [stop(i, east=i, stay=120) for i in range(7)]
    result = replan([], stops, protected=[s.id for s in stops])
    assert len(result.day.visits) == 7
    assert result.over == []
    assert result.end_min > DAY.end_min + REPLAN_GRACE_MIN


def test_closed_places_are_dropped_unless_protected() -> None:
    origin = Origin(HOTEL.lat, HOTEL.lon, minute=19 * H + 15)
    museum = stop(0, east=1, stay=None, category="museum", hours="day")
    square = stop(1, east=2)
    result = replan([], [museum, square], origin=origin)
    assert ids(result) == [square.id]
    assert result.closed == [museum]

    kept = replan([], [museum, square], origin=origin, protected=[museum.id])
    assert museum.id in ids(kept)
    assert kept.late == [museum]


def test_the_stay_decides_the_visit_length() -> None:
    result = replan([], [stop(0, east=1, stay=25, category="museum")])
    [visit] = result.day.visits
    assert visit.leave_min - visit.arrive_min == 25


def test_an_open_ended_day_without_a_hotel() -> None:
    result = replan([stop(0)], [stop(1, east=2), stop(2, east=1)], start=None)
    assert ids(result) == [100, 102, 101]
    assert result.day.visits[0].leg is None  # a free start
    assert result.day.return_leg is None


def test_no_time_left() -> None:
    late = Origin(HOTEL.lat, HOTEL.lon, minute=DAY.end_min + REPLAN_GRACE_MIN)
    with pytest.raises(NothingFitsError):
        replan([], [stop(0)], origin=late)
    with pytest.raises(ValueError, match="first stop"):
        replan([stop(0)], [stop(1)], first=100)
