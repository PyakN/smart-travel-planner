"""Days with their own hours, and places with opening hours (time windows)."""

import asyncio
import random
from collections.abc import Sequence
from math import inf

import pytest

from app.catalog import VisitHours
from app.optimizer.distance import HaversineProvider
from app.optimizer.planner import (
    DAY_BUDGET_MIN,
    NIGHT_START_MIN,
    DayWindow,
    NothingFitsError,
    RoutePlan,
    StartPoint,
    Stop,
    plan_route,
)
from app.schemas.trip import Pace

H = 60
SUNSET = 17 * H + 36
AFTERNOON = DayWindow(16 * H, 21 * H + 30, sunrise_min=7 * H, sunset_min=SUNSET)
# From 16:00 until 03:00 the next morning.
OVERNIGHT = DayWindow(16 * H, 27 * H, sunrise_min=7 * H, sunset_min=SUNSET)


def stop(
    i: int,
    lat: float,
    lon: float,
    category: str = "landmark",
    hours: VisitHours = "any",
    *,
    outdoor: bool = False,
) -> Stop:
    return Stop(100 + i, lat, lon, category, priority=i, outdoor=outdoor, hours=hours)


def plan(
    stops: Sequence[Stop],
    windows: Sequence[DayWindow] | None,
    days: int = 1,
    pace: Pace = "moderate",
    start: StartPoint | None = None,
) -> RoutePlan:
    return asyncio.run(
        plan_route(
            stops,
            days=days,
            pace=pace,
            provider=HaversineProvider(),
            start=start,
            modes=("walk",),
            windows=windows,
        )
    )


def times(route: RoutePlan, day: int = 0) -> dict[int, tuple[int, int]]:
    return {v.stop.id: (v.arrive_min, v.leave_min) for v in route.days[day].visits}


def test_default_hours_are_the_full_day() -> None:
    window = DayWindow()
    assert (window.start_min, window.end_min) == (9 * H + 30, 21 * H + 30)
    for pace, budget in DAY_BUDGET_MIN.items():
        assert window.budget(pace) == budget


def test_the_pace_is_a_share_of_the_hours() -> None:
    assert AFTERNOON.budget("moderate") == 220  # two thirds of 5 h 30 min
    assert OVERNIGHT.length_min == 11 * H
    assert OVERNIGHT.budget("relaxed") == 330
    assert OVERNIGHT.budget("intense") == 550


@pytest.mark.parametrize(("start", "end"), [(10 * H, 10 * H), (12 * H, 9 * H), (H, 26 * H)])
def test_impossible_hours(start: int, end: int) -> None:
    with pytest.raises(ValueError, match="no such day hours"):
        DayWindow(start, end)


def test_opening_by_visit_hours() -> None:
    assert OVERNIGHT.opening("day") == (-inf, NIGHT_START_MIN)
    assert OVERNIGHT.opening("night") == (NIGHT_START_MIN, inf)
    assert OVERNIGHT.opening("daylight") == (7 * H, SUNSET)
    assert OVERNIGHT.opening("any") == (-inf, inf)
    assert DayWindow().opening("daylight") == (-inf, inf)  # daylight unknown


# Six landmarks along a street, 300 m apart: 45 min each and 4.5 min of walking between.
STREET = [stop(i, 38.7100, -9.1400 + 0.0035 * i) for i in range(6)]


def test_a_late_start_holds_fewer_stops() -> None:
    assert len(plan(STREET, None).days[0].visits) == 6
    route = plan(STREET, [AFTERNOON])
    [day] = route.days
    assert day.visits[0].arrive_min == 16 * H
    assert len(day.visits) == 4  # 3 h 40 min of sightseeing
    assert day.total_min <= 220
    assert [s.priority for s in route.dropped] == [4, 5]
    assert route.warnings == ["dropped 2 stop(s) to fit 3 h 40 min days"]


# An evening in Chiado and Bairro Alto, the evening places most important.
BAIRRO_ALTO = [
    stop(0, 38.7128, -9.1455, "nightlife", "night"),
    stop(1, 38.7120, -9.1462, "nightlife", "night"),
    stop(2, 38.7110, -9.1440, "restaurant", "night"),
    stop(3, 38.7097, -9.1415, "museum", "day"),
    stop(4, 38.7154, -9.1443, "viewpoint", "daylight", outdoor=True),
]


def test_sights_come_first_and_evening_places_wait_for_the_night() -> None:
    route = plan(BAIRRO_ALTO, [OVERNIGHT])
    assert route.dropped == []
    [day] = route.days
    visits = {v.stop.id: v for v in day.visits}
    viewpoint, museum = visits[104], visits[103]
    assert viewpoint.leave_min <= SUNSET
    assert museum.leave_min <= NIGHT_START_MIN
    night = [v for v in day.visits if v.stop.hours == "night"]
    assert [v.stop.id for v in day.visits[-3:]] == [v.stop.id for v in night]
    assert night[0].arrive_min == NIGHT_START_MIN
    assert night[0].wait_min > 60  # free time between the museum and the first bar
    assert day.total_min <= OVERNIGHT.budget("moderate")


def test_nothing_is_visited_after_closing_or_in_the_dark() -> None:
    late_night = DayWindow(21 * H, 27 * H, sunrise_min=7 * H, sunset_min=SUNSET)
    route = plan(BAIRRO_ALTO, [late_night])
    assert {s.id for s in route.dropped} == {103, 104}
    assert route.warnings == ["dropped 2 stop(s) that are closed or dark in the day's hours"]
    assert all(v.stop.hours == "night" for v in route.days[0].visits)
    with pytest.raises(NothingFitsError):
        plan(BAIRRO_ALTO[3:4], [late_night])


def test_bars_after_midnight() -> None:
    bars = [stop(i, 38.7128 + 0.0005 * i, -9.1455, "nightlife", "night") for i in range(3)]
    route = plan(bars, [DayWindow(22 * H, 27 * H)])
    assert len(route.days[0].visits) == 3
    last = route.days[0].visits[-1]
    assert 24 * H < last.arrive_min < last.leave_min <= 27 * H


def test_free_time_at_the_hotel_before_the_evening() -> None:
    hotel = StartPoint(38.7139, -9.1394)  # Rossio
    route = plan(BAIRRO_ALTO[:1], [DayWindow(18 * H, 24 * H)], start=hotel)
    [visit] = route.days[0].visits
    assert visit.arrive_min == NIGHT_START_MIN
    assert visit.leg is not None
    assert visit.wait_min == round(NIGHT_START_MIN - 18 * H - visit.leg.minutes)


def test_a_short_first_day_takes_fewer_stops() -> None:
    stops = [stop(i, 38.7100 + 0.0004 * (i % 2), -9.1400 + 0.0035 * i) for i in range(9)]
    route = plan(stops, [AFTERNOON, DayWindow()], days=2)
    assert route.dropped == []
    first, second = route.days
    assert (first.day, second.day) == (1, 2)
    assert first.visits[0].arrive_min == 16 * H
    assert second.visits[0].arrive_min == 9 * H + 30
    assert len(first.visits) <= 4 < len(second.visits)
    assert first.total_min <= 220 and second.total_min <= 480


HOURS: tuple[VisitHours, ...] = ("any", "day", "daylight", "night")
CATEGORY: dict[VisitHours, str] = {
    "any": "landmark",
    "day": "museum",
    "daylight": "viewpoint",
    "night": "nightlife",
}


@pytest.mark.parametrize("seed", range(20))
def test_plans_keep_every_day_to_its_hours(seed: int) -> None:
    rng = random.Random(seed)
    days = rng.randint(1, 3)
    pace: Pace = rng.choice(["relaxed", "moderate", "intense"])
    windows = []
    for _ in range(days):
        start = rng.randrange(8 * H, 18 * H, 30)
        end = start + rng.randrange(4 * H, 15 * H, 30)
        windows.append(DayWindow(start, end, sunrise_min=7 * H, sunset_min=18 * H))
    stops = []
    for i in range(rng.randint(6, 16)):
        hours = rng.choice(HOURS)
        lat, lon = 38.71 + rng.uniform(-0.01, 0.01), -9.14 + rng.uniform(-0.012, 0.012)
        stops.append(stop(i, lat, lon, CATEGORY[hours], hours, outdoor=hours == "daylight"))
    try:
        route = plan(stops, windows, days=days, pace=pace)
    except NothingFitsError:
        return
    planned = [v.stop.id for day in route.days for v in day.visits]
    assert sorted(planned + [s.id for s in route.dropped]) == [s.id for s in stops]
    for day in route.days:
        window = windows[day.day - 1]
        assert day.window == window
        assert day.total_min <= window.budget(pace) or len(day.visits) == 1
        assert window.start_min <= day.visits[0].arrive_min
        for v in day.visits:
            opens, closes = window.opening(v.stop.hours)
            assert opens <= v.arrive_min and v.leave_min <= closes
