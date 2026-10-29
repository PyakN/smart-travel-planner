"""Places with opening hours of their own (OSM), on the trip's dates."""

import asyncio
from collections.abc import Sequence
from datetime import date
from math import inf

from app.catalog import VisitHours
from app.optimizer.distance import HaversineProvider
from app.optimizer.planner import (
    NIGHT_START_MIN,
    DayReplan,
    DayWindow,
    Origin,
    RoutePlan,
    Span,
    StartPoint,
    Stop,
    plan_route,
    replan_day,
)
from app.schemas.trip import Pace

H = 60
MONDAY, TUESDAY = date(2026, 11, 2), date(2026, 11, 3)
SUNSET = 17 * H + 36
DAY = DayWindow(9 * H + 30, 21 * H + 30, sunrise_min=7 * H, sunset_min=SUNSET, on=TUESDAY)
TEN_TO_SIX: tuple[Span, ...] = ((10 * H, 18 * H),)


def stop(
    i: int,
    lat: float,
    lon: float,
    category: str = "landmark",
    hours: VisitHours = "day",
    opening_hours: dict[date, tuple[Span, ...]] | None = None,
) -> Stop:
    return Stop(100 + i, lat, lon, category, priority=i, hours=hours, opening_hours=opening_hours)


def plan(
    stops: Sequence[Stop],
    windows: Sequence[DayWindow],
    *,
    start: StartPoint | None = None,
    pace: Pace = "moderate",
) -> RoutePlan:
    return asyncio.run(
        plan_route(
            stops,
            days=len(windows),
            pace=pace,
            provider=HaversineProvider(),
            start=start,
            modes=("walk",),
            windows=windows,
        )
    )


def visits(route: RoutePlan) -> dict[int, tuple[int, int, int]]:
    """(day, arrive, leave) by stop id."""
    return {v.stop.id: (d.day, v.arrive_min, v.leave_min) for d in route.days for v in d.visits}


def test_own_hours_replace_the_hours_of_the_kind() -> None:
    museum = stop(0, 38.71, -9.14, "museum", opening_hours={TUESDAY: TEN_TO_SIX})
    assert DAY.spans(museum) == TEN_TO_SIX  # not until 20:00
    assert DayWindow().spans(museum) == ((-inf, NIGHT_START_MIN),)  # no date: the kind's
    assert DayWindow(on=MONDAY).spans(museum) == ((-inf, NIGHT_START_MIN),)  # unknown then
    late = stop(1, 38.71, -9.14, "museum", opening_hours={TUESDAY: ((10 * H, 22 * H),)})
    assert DAY.spans(late) == ((10 * H, 22 * H),)  # open after 20:00 too


def test_own_hours_within_daylight_the_evening_and_the_days_hours() -> None:
    park = stop(0, 38.71, -9.14, "park", "daylight", {TUESDAY: ((8 * H, 22 * H),)})
    assert DAY.spans(park) == ((8 * H, SUNSET),)
    bar = stop(1, 38.71, -9.14, "nightlife", "night", {TUESDAY: ((17 * H, 26 * H),)})
    assert DAY.spans(bar) == ((NIGHT_START_MIN, 26 * H),)
    lunch = {TUESDAY: ((10 * H, 13 * H), (14 * H, 18 * H), (34 * H, 42 * H))}
    museum = stop(2, 38.71, -9.14, "museum", opening_hours=lunch)
    # The next day's hours are past this day's end.
    assert DAY.spans(museum) == ((10 * H, 13 * H), (14 * H, 18 * H))
    closed = stop(3, 38.71, -9.14, "museum", opening_hours={TUESDAY: ()})
    assert DAY.spans(closed) == ()
    assert not DAY.can_visit(closed)
    morning = stop(4, 38.71, -9.14, "market", opening_hours={TUESDAY: ((7 * H, 10 * H),)})
    assert DAY.spans(morning) == ((7 * H, 10 * H),)
    assert not DAY.can_visit(morning)  # 40 min from 09:30 is past 10:00
    assert DAY.can_visit(museum)


# Six landmarks along a street, 300 m apart: 45 min each and 4.5 min of walking between.
STREET = [stop(i, 38.7100, -9.1400 + 0.0035 * i) for i in range(6)]


def test_a_place_that_closes_early_is_visited_before_it_closes() -> None:
    # The street's far end is visited last, from 13:00 on, but closes at 13:00.
    by_lunch = stop(6, 38.7100, -9.1400 + 0.0035 * 6, opening_hours={TUESDAY: ((9 * H, 13 * H),)})
    route = plan([*STREET, by_lunch], [DAY], pace="intense")
    assert route.dropped == []
    day, _, leave = visits(route)[by_lunch.id]
    assert leave <= 13 * H


def test_a_visit_waits_out_a_lunch_break() -> None:
    lunch = {TUESDAY: ((10 * H, 13 * H), (14 * H, 18 * H))}
    museum = stop(0, 38.7100, -9.1400, "museum", opening_hours=lunch)  # a 90-minute visit
    hotel = StartPoint(38.7101, -9.1401)
    noon = DayWindow(12 * H, 21 * H + 30, on=TUESDAY)
    [visit] = plan([museum], [noon], start=hotel).days[0].visits
    assert (visit.arrive_min, visit.leave_min) == (14 * H, 15 * H + 30)
    assert visit.wait_min > 60


def test_a_place_closed_on_one_day_goes_on_another() -> None:
    # Monday holds the museum's neighbourhood, but the museum is closed on Mondays; a
    # shorter Tuesday in a neighbourhood 1.7 km away has room for it.
    first = [stop(i, 38.7100, -9.1400 + 0.0035 * i) for i in range(5)]
    second = [stop(5 + i, 38.7250, -9.1400 + 0.0035 * i) for i in range(2)]
    museum = stop(7, 38.7105, -9.1380, "museum", opening_hours={MONDAY: (), TUESDAY: TEN_TO_SIX})
    windows = [DayWindow(on=MONDAY), DayWindow(13 * H, 21 * H + 30, on=TUESDAY)]
    route = plan([museum, *first, *second], windows)
    assert route.dropped == []
    assert route.warnings == []
    day, _, leave = visits(route)[museum.id]
    assert day == 2 and leave <= 18 * H


def test_a_place_closed_on_every_day_is_dropped() -> None:
    museum = stop(6, 38.7105, -9.1380, "museum", opening_hours={MONDAY: (), TUESDAY: ()})
    windows = [DayWindow(on=MONDAY), DayWindow(on=TUESDAY)]
    route = plan([museum, *STREET], windows)
    assert [s.id for s in route.dropped] == [museum.id]
    assert route.warnings == ["dropped 1 stop(s) that are closed or dark in the day's hours"]


def test_days_with_the_same_hours_keep_their_dates_for_places_with_own_hours() -> None:
    # The most important stop would go on day 1, but it is closed on Mondays.
    museum = stop(0, 38.7105, -9.1380, "museum", opening_hours={MONDAY: (), TUESDAY: TEN_TO_SIX})
    others = [stop(1 + i, 38.7250, -9.1400 + 0.0035 * i) for i in range(3)]
    route = plan([museum, *others], [DayWindow(on=MONDAY), DayWindow(on=TUESDAY)])
    assert route.dropped == []
    assert visits(route)[museum.id][0] == 2


def test_a_replanned_day_keeps_its_places_own_hours() -> None:
    museum = stop(0, 38.7105, -9.1380, "museum", opening_hours={TUESDAY: TEN_TO_SIX})
    square = stop(1, 38.7110, -9.1370)
    hotel = StartPoint(38.7100, -9.1400)
    at_five = Origin(hotel.lat, hotel.lon, minute=17 * H)  # 90 minutes before 18:00 no more

    def replan(protected: Sequence[int] = ()) -> DayReplan:
        return asyncio.run(
            replan_day(
                [],
                [museum, square],
                window=DAY,
                provider=HaversineProvider(),
                start=hotel,
                origin=at_five,
                protected=protected,
                modes=("walk",),
            )
        )

    result = replan()
    assert [v.stop.id for v in result.day.visits] == [square.id]
    assert result.closed == [museum]
    kept = replan(protected=[museum.id])
    assert kept.late == [museum]


def test_only_stops_whose_leaving_helps_are_dropped_for_their_hours() -> None:
    # From 16:25 the museum, 9 minutes' walk away, ends 4 minutes after it closes at 18:00,
    # whatever the order; dropping the less important church (open until 20:00) is no help.
    here = Origin(38.7100, -9.1400, minute=16 * H + 25)
    museum = stop(0, 38.7140, -9.1400, "museum", opening_hours={TUESDAY: TEN_TO_SIX})
    church = stop(1, 38.7102, -9.1402, "religious")
    result = asyncio.run(
        replan_day(
            [],
            [museum, church],
            window=DAY,
            provider=HaversineProvider(),
            origin=here,
            modes=("walk",),
        )
    )
    assert [v.stop.id for v in result.day.visits] == [church.id]
    assert result.closed == [museum]


def test_a_place_closed_on_its_day_takes_the_place_of_a_lesser_stop() -> None:
    # Two full days along a street; the most important stop is a museum closed on Mondays.
    street = [stop(1 + i, 38.7100, -9.1400 + 0.0035 * i) for i in range(14)]
    museum = stop(0, 38.7103, -9.1400, "museum", opening_hours={MONDAY: (), TUESDAY: TEN_TO_SIX})
    route = plan([museum, *street], [DayWindow(on=MONDAY), DayWindow(on=TUESDAY)])
    assert visits(route)[museum.id][0] == 2
    assert [s.priority for s in route.dropped] == [14]  # the least important instead
    assert route.warnings == ["dropped 1 stop(s) to fit 8 h days"]
