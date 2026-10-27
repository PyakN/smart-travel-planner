"""Weather-aware plans: outdoor stops go where the day is dry and light."""

import asyncio
import random
from collections.abc import Sequence

import pytest

from app.optimizer.distance import HaversineProvider
from app.optimizer.planner import (
    DAY_BUDGET_MIN,
    OUTDOOR_PENALTY_MIN,
    DayConditions,
    RoutePlan,
    Stop,
    plan_route,
)
from app.schemas.trip import Pace

NOON = 12 * 60


def conditions(
    *bad: tuple[float, float, float], sunrise: float = 7, sunset: float = 19
) -> DayConditions:
    """Badness over hour ranges, (from, to, badness); dark outside sunrise..sunset."""
    minutes = [0.0] * 24 * 60
    for start, end, badness in bad:
        for m in range(round(start * 60), round(end * 60)):
            minutes[m] = badness
    for m in range(len(minutes)):
        if not sunrise * 60 <= m < sunset * 60:
            minutes[m] = 1.0
    return DayConditions.from_minutes(minutes)


DRY = conditions()
RAIN_ALL_DAY = conditions((0, 24, 1.0))


def stop(i: int, lat: float, lon: float, category: str, outdoor: bool) -> Stop:
    return Stop(100 + i, lat, lon, category, priority=i, outdoor=outdoor)


def plan(
    stops: Sequence[Stop],
    weather: Sequence[DayConditions] | None,
    days: int = 1,
    pace: Pace = "moderate",
) -> RoutePlan:
    return asyncio.run(
        plan_route(
            stops,
            days=days,
            pace=pace,
            provider=HaversineProvider(),
            modes=("walk",),
            conditions=weather,
        )
    )


def ids(route: RoutePlan) -> list[list[int]]:
    return [[v.stop.id for v in day.visits] for day in route.days]


def outdoor_visits(route: RoutePlan, day: int = 0) -> list[tuple[int, int]]:
    return [(v.arrive_min, v.leave_min) for v in route.days[day].visits if v.stop.outdoor]


def weather_cost(route: RoutePlan, weather: Sequence[DayConditions]) -> float:
    """What a weather-aware plan minimises: travel minutes plus the outdoor penalty."""
    total = 0.0
    for day, today in zip(route.days, weather, strict=False):
        legs = [v.leg for v in day.visits] + [day.return_leg]
        total += sum(leg.minutes for leg in legs if leg is not None)
        total += OUTDOOR_PENALTY_MIN * sum(
            today.bad_share(v.arrive_min, v.leave_min) for v in day.visits if v.stop.outdoor
        )
    return total


def test_bad_share() -> None:
    day = DayConditions.from_minutes([0.0] * 600 + [1.0] * 840)
    assert day.bad_share(560, 590) == 0.0
    assert day.bad_share(590, 610) == 0.5
    assert day.bad_share(1430, 1450) == 1.0  # past midnight counts like the last minute
    assert day.bad_share(600, 600) == 0.0
    with pytest.raises(ValueError, match="at least one minute"):
        DayConditions.from_minutes([])


# Two viewpoints and two museums along a street, 300 m apart, viewpoints first.
STREET = [
    stop(0, 38.7100, -9.1400, "viewpoint", outdoor=True),
    stop(1, 38.7100, -9.1365, "viewpoint", outdoor=True),
    stop(2, 38.7100, -9.1330, "museum", outdoor=False),
    stop(3, 38.7100, -9.1295, "museum", outdoor=False),
]


def test_a_rainy_morning_goes_to_the_museums() -> None:
    assert ids(plan(STREET, None)) == [[100, 101, 102, 103]]
    rainy_morning = [conditions((8, 12, 1.0))]
    route = plan(STREET, rainy_morning)
    assert ids(route) == [[103, 102, 101, 100]]  # same street, walked the other way
    assert all(arrive >= NOON for arrive, _ in outdoor_visits(route))


def test_viewpoints_end_by_sunset() -> None:
    museums_then_view = [
        stop(0, 38.7100, -9.1400, "museum", outdoor=False),
        stop(1, 38.7100, -9.1365, "museum", outdoor=False),
        stop(2, 38.7100, -9.1330, "museum", outdoor=False),
        stop(3, 38.7100, -9.1295, "viewpoint", outdoor=True),
    ]
    early_sunset = [conditions(sunset=13)]
    [(arrive, _)] = outdoor_visits(plan(museums_then_view, None, pace="intense"))
    assert arrive > 13 * 60
    route = plan(museums_then_view, early_sunset, pace="intense")
    [(_, leave)] = outdoor_visits(route)
    assert leave <= 13 * 60


def test_days_go_on_the_dates_that_suit_them() -> None:
    # Outdoor sights in Belém, the most important ones, and museums 6 km away.
    belem = [
        stop(0, 38.6970, -9.2060, "viewpoint", outdoor=True),
        stop(1, 38.6960, -9.2040, "park", outdoor=True),
        stop(2, 38.6950, -9.2075, "monument", outdoor=True),
    ]
    centre = [
        stop(3, 38.7200, -9.1350, "museum", outdoor=False),
        stop(4, 38.7210, -9.1330, "gallery", outdoor=False),
        stop(5, 38.7190, -9.1370, "religious", outdoor=False),
    ]
    stops = belem + centre
    belem_ids = {s.id for s in belem}
    assert set(ids(plan(stops, None, days=2))[0]) == belem_ids  # most important first
    route = plan(stops, [RAIN_ALL_DAY, DRY], days=2)
    assert set(ids(route)[1]) == belem_ids
    assert not outdoor_visits(route, day=0)


def two_neighbourhoods(gap_lon: float) -> list[Stop]:
    """Museums and a viewpoint on one side, viewpoints and a museum `gap_lon` east."""
    east = -9.1400 + gap_lon
    return [
        stop(0, 38.7100, -9.1400, "museum", outdoor=False),
        stop(1, 38.7110, -9.1410, "museum", outdoor=False),
        stop(2, 38.7105, -9.1390, "viewpoint", outdoor=True),
        stop(3, 38.7100, east, "viewpoint", outdoor=True),
        stop(4, 38.7110, east - 0.001, "viewpoint", outdoor=True),
        stop(5, 38.7105, east + 0.001, "museum", outdoor=False),
    ]


def test_outdoor_stops_trade_days_with_nearby_indoor_ones() -> None:
    stops = two_neighbourhoods(gap_lon=0.006)  # 500 m
    route = plan(stops, [RAIN_ALL_DAY, DRY], days=2)
    assert not outdoor_visits(route, day=0)
    assert {v.stop.id for v in route.days[1].visits if v.stop.outdoor} == {102, 103, 104}


def test_no_trades_across_town() -> None:
    stops = two_neighbourhoods(gap_lon=0.06)  # 5 km: an hour and a half each way on foot
    route = plan(stops, [RAIN_ALL_DAY, DRY], days=2)
    assert [v.stop.id for v in route.days[0].visits if v.stop.outdoor] == [102]


def test_fine_weather_changes_nothing() -> None:
    rng = random.Random(7)
    stops = [
        stop(
            i,
            38.71 + rng.uniform(-0.01, 0.01),
            -9.14 + rng.uniform(-0.012, 0.012),
            rng.choice(["viewpoint", "museum", "park", "religious", "landmark"]),
            outdoor=rng.random() < 0.5,
        )
        for i in range(12)
    ]
    assert ids(plan(stops, [DRY, DRY], days=2)) == ids(plan(stops, None, days=2))


def test_conditions_for_every_day() -> None:
    with pytest.raises(ValueError, match="1 of 2 days"):
        plan(STREET, [DRY], days=2)


@pytest.mark.parametrize("seed", range(15))
def test_weather_plans_keep_the_stops_and_the_budget(seed: int) -> None:
    rng = random.Random(seed)
    days = rng.randint(1, 3)
    pace: Pace = rng.choice(["relaxed", "moderate", "intense"])
    stops = [
        Stop(
            i,
            38.71 + rng.uniform(-0.015, 0.015),
            -9.14 + rng.uniform(-0.02, 0.02),
            rng.choice(["viewpoint", "museum", "park", "religious", "monument", "market"]),
            priority=i,
            required=rng.random() < 0.15,
            outdoor=rng.random() < 0.5,
        )
        for i in range(rng.randint(4, 14))
    ]
    weather = []
    for _ in range(days):
        start = rng.uniform(8, 18)
        rain = (start, start + rng.uniform(1, 6), rng.choice([0.5, 0.8, 1.0]))
        weather.append(conditions(rain, sunset=rng.uniform(16, 20)))

    plain, aware = plan(stops, None, days, pace), plan(stops, weather, days, pace)
    # The same stops, only on other days or in another order; no day over its budget.
    assert sorted(i for day in ids(aware) for i in day) == sorted(i for d in ids(plain) for i in d)
    assert all(day.total_min <= DAY_BUDGET_MIN[pace] for day in aware.days)
    # Never worse for what it minimises than the plan made without weather.
    assert weather_cost(aware, weather) <= weather_cost(plain, weather) + 0.5
