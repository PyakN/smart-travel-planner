import asyncio
import random
from collections.abc import Collection, Sequence
from math import inf

import pytest

from app.optimizer.days import day_sizes
from app.optimizer.distance import HaversineProvider, haversine_matrix
from app.optimizer.geometry import LatLon
from app.optimizer.planner import (
    ALL_MODES,
    DAY_START_MIN,
    TRANSIT_FIRST_MIN_DISTANCE_M,
    TRANSIT_M_PER_MIN,
    TRANSIT_MIN_DISTANCE_M,
    TRANSIT_OVERHEAD_MIN,
    WALKING_M_PER_MIN,
    RoutePlan,
    StartPoint,
    Stop,
    TravelMode,
    plan_route,
    transit_threshold_m,
    travel_leg,
)
from app.optimizer.tsp import path_cost
from app.schemas.trip import Pace

ROSSIO = StartPoint(38.7139, -9.1394)


def stop(i: int, lat: float, lon: float, category: str = "monument") -> Stop:
    return Stop(id=100 + i, lat=lat, lon=lon, category=category, priority=i)


def plan(
    stops: Sequence[Stop],
    days: int = 1,
    pace: Pace = "intense",
    start: StartPoint | None = None,
    enforce_budget: bool = False,
    modes: Collection[TravelMode] = ("walk",),  # distance guarantees below are about walking
) -> RoutePlan:
    return asyncio.run(
        plan_route(
            stops,
            days=days,
            pace=pace,
            provider=HaversineProvider(),
            start=start,
            enforce_budget=enforce_budget,
            modes=modes,
        )
    )


def ids(plan_: RoutePlan) -> list[list[int]]:
    return [[v.stop.id for v in day.visits] for day in plan_.days]


def naive_cost(stops: Sequence[Stop], days: int, start: StartPoint | None) -> float:
    """Selection order cut into balanced consecutive days, as an LLM-only planner would."""
    points = [LatLon(s.lat, s.lon) for s in stops] + (
        [LatLon(start.lat, start.lon)] if start else []
    )
    m = haversine_matrix(points)
    order = sorted(range(len(stops)), key=lambda i: stops[i].priority)
    low, high = day_sizes(len(stops), days)
    sizes = [high] * (len(stops) % days) + [low] * (days - len(stops) % days)
    total, pos = 0.0, 0
    for size in sizes:
        chunk = order[pos : pos + size]
        pos += size
        path = ([len(stops)] if start else []) + chunk
        if start and start.round_trip:
            path.append(len(stops))
        total += path_cost(m, path)
    return total


def test_single_day_untangles_a_zigzag() -> None:
    # Priority order zigzags along a street; the optimizer walks it end to end.
    lons = [-9.140, -9.130, -9.138, -9.132, -9.136, -9.134]
    stops = [stop(i, 38.71, lon) for i, lon in enumerate(lons)]
    result = plan(stops)
    walked = [s.lon for s in (v.stop for v in result.days[0].visits)]
    assert walked in (sorted(walked), sorted(walked, reverse=True))
    assert result.self_intersections == 0
    assert result.total_distance_m < naive_cost(stops, 1, None) / 2.5


def test_days_follow_neighbourhoods() -> None:
    alfama = [stop(i, 38.711 + i * 0.001, -9.130) for i in range(3)]
    belem = [stop(3 + i, 38.697 + i * 0.001, -9.206) for i in range(3)]
    avenidas = [stop(6 + i, 38.737 + i * 0.001, -9.150) for i in range(3)]
    # Interleave priorities so the selection order hops across the city.
    shuffled = [
        Stop(s.id, s.lat, s.lon, s.category, p)
        for p, s in enumerate(
            [
                alfama[0],
                belem[0],
                avenidas[0],
                alfama[1],
                belem[1],
                avenidas[1],
                alfama[2],
                belem[2],
                avenidas[2],
            ]
        )
    ]
    result = plan(shuffled, days=3)
    neighbourhoods = [{s.id for s in group} for group in (alfama, belem, avenidas)]
    assert [set(day) for day in ids(result)] == neighbourhoods  # day 1 has the top-priority stop
    assert result.total_distance_m < naive_cost(shuffled, 3, None) / 3


def dense_and_sparse() -> list[Stop]:
    # 9 viewpoints within ~600 m of each other in Alfama, 3 spread out across the city.
    dense = [
        stop(i, 38.711 + 0.0007 * (i % 3), -9.131 + 0.0007 * (i // 3), "viewpoint")
        for i in range(9)
    ]
    sparse = [
        stop(9, 38.697, -9.206, "viewpoint"),
        stop(10, 38.737, -9.150, "viewpoint"),
        stop(11, 38.748, -9.170, "viewpoint"),
    ]
    return dense + sparse


def test_days_are_balanced_by_time_not_by_count() -> None:
    result = plan(dense_and_sparse(), days=2, pace="moderate")
    sizes = sorted(len(d.visits) for d in result.days)
    assert sizes != [6, 6]  # equal counts would make each day cross the city
    assert all(d.total_min <= 8 * 60 for d in result.days)


def test_rebalancing_respects_the_time_budget() -> None:
    # Same geography, but museums: 9 x 90 min does not fit one day, so days stay balanced.
    museums = [Stop(s.id, s.lat, s.lon, "museum", s.priority) for s in dense_and_sparse()]
    result = plan(museums, days=2, pace="intense")  # 10 h budget
    assert max(len(d.visits) for d in result.days) <= 6


@pytest.mark.parametrize(
    "start",
    [None, ROSSIO, StartPoint(ROSSIO.lat, ROSSIO.lon, round_trip=True)],
    ids=["free", "hotel", "hotel-round-trip"],
)
def test_never_longer_than_selection_order(start: StartPoint | None) -> None:
    rng = random.Random(3)
    for _ in range(15):
        n, days = rng.randint(4, 24), rng.randint(1, 4)
        stops = [stop(i, rng.uniform(38.69, 38.76), rng.uniform(-9.22, -9.10)) for i in range(n)]
        result = plan(stops, days=days, start=start)
        assert result.total_distance_m <= naive_cost(stops, days, start) + 1e-6
        assert sorted(v.stop.id for d in result.days for v in d.visits) == [s.id for s in stops]


def test_hotel_round_trip_legs() -> None:
    stops = [stop(0, 38.7075, -9.1364), stop(1, 38.7116, -9.1301)]
    result = plan(stops, start=StartPoint(ROSSIO.lat, ROSSIO.lon, round_trip=True))
    day = result.days[0]
    first_leg = day.visits[0].leg
    assert first_leg is not None and first_leg.distance_m > 0
    walked = sum(v.leg.distance_m for v in day.visits if v.leg)
    assert day.return_leg is not None
    assert day.distance_m == pytest.approx(walked + day.return_leg.distance_m)


def test_schedule_times() -> None:
    stops = [stop(0, 38.71, -9.140, "museum"), stop(1, 38.71, -9.130, "viewpoint")]
    first, second = plan(stops).days[0].visits
    assert (first.arrive_min, first.leave_min) == (DAY_START_MIN, DAY_START_MIN + 90)
    assert first.leg is None  # free start
    assert second.leg is not None and second.leg.mode == "walk"
    expected_arrival = first.leave_min + second.leg.distance_m / WALKING_M_PER_MIN
    assert second.arrive_min == round(expected_arrival)
    assert second.leave_min == second.arrive_min + 20


def test_budget_drops_least_important_stops() -> None:
    # 3 museums (90 min) + 2 landmarks (45 min) = 6 h of visits, plus walking: over 6 h.
    categories = ["museum", "museum", "museum", "landmark", "landmark"]
    stops = [stop(i, 38.71 + i * 0.001, -9.14, c) for i, c in enumerate(categories)]
    result = plan(stops, pace="relaxed", enforce_budget=True)
    assert [s.priority for s in result.dropped] == [4]
    assert result.days[0].total_min <= 6 * 60
    assert result.warnings == ["dropped 1 stop(s) to fit 6 h days"]
    assert len(plan(stops, pace="relaxed").days[0].visits) == 5  # budget off


def test_more_days_than_stops() -> None:
    result = plan([stop(0, 38.71, -9.14), stop(1, 38.72, -9.15)], days=4)
    assert len(result.days) == 2
    assert "only 2 stops for 4 days" in result.warnings[0]


def test_empty_input() -> None:
    with pytest.raises(ValueError):
        plan([])


def test_reports_distance_source() -> None:
    assert plan([stop(0, 38.71, -9.14)]).distance_source == "haversine"


BELEM_TOWER = (38.6916, -9.2160)
CENTRE = [(38.7075, -9.1364), (38.7116, -9.1301), (38.7139, -9.1335)]


def test_travel_leg_modes() -> None:
    assert travel_leg(2000).mode == "walk"
    leg = travel_leg(7000)
    assert leg.mode == "transit"
    assert leg.minutes == pytest.approx(TRANSIT_OVERHEAD_MIN + 7000 / TRANSIT_M_PER_MIN)
    assert leg.minutes < travel_leg(7000, inf).minutes
    assert travel_leg(7000, inf).mode == "walk"
    assert travel_leg(1500, TRANSIT_FIRST_MIN_DISTANCE_M).mode == "transit"


@pytest.mark.parametrize(
    ("modes", "expected"),
    [
        (("walk",), inf),
        (("walk", "transit"), TRANSIT_MIN_DISTANCE_M),
        (("transit",), TRANSIT_FIRST_MIN_DISTANCE_M),
    ],
)
def test_transit_threshold(modes: tuple[TravelMode, ...], expected: float) -> None:
    assert transit_threshold_m(modes) == expected


def test_no_travel_mode_is_an_error() -> None:
    with pytest.raises(ValueError):
        plan([stop(0, 38.71, -9.14)], modes=())


def test_long_legs_use_transit() -> None:
    stops = [stop(i, lat, lon, "landmark") for i, (lat, lon) in enumerate([*CENTRE, BELEM_TOWER])]
    hotel = StartPoint(ROSSIO.lat, ROSSIO.lon)
    by_transit = plan(stops, start=hotel, modes=ALL_MODES)
    on_foot = plan(stops, start=hotel)

    [day] = by_transit.days
    modes = [v.leg.mode for v in day.visits if v.leg]
    assert modes.count("transit") == day.transit_legs == 1
    assert day.walking_m < day.distance_m
    assert day.total_min < on_foot.days[0].total_min
    assert on_foot.days[0].transit_legs == 0
    assert on_foot.days[0].walking_m == pytest.approx(on_foot.days[0].distance_m)


def test_transit_keeps_far_places_on_a_feasible_day() -> None:
    # Hotel in the centre, 2 relaxed days: walking to Belem eats the budget, transit does not.
    belem = [stop(10 + i, 38.6916 + 0.002 * i, -9.2160 + 0.004 * i, "landmark") for i in range(3)]
    centre = [stop(i, lat, lon, "landmark") for i, (lat, lon) in enumerate(CENTRE)]
    stops = centre + belem
    hotel = StartPoint(ROSSIO.lat, ROSSIO.lon, round_trip=True)
    result = plan(stops, days=2, pace="relaxed", start=hotel, modes=ALL_MODES, enforce_budget=True)
    assert result.dropped == []
    assert {frozenset(v.stop.id for v in d.visits) for d in result.days} == {
        frozenset(s.id for s in centre),
        frozenset(s.id for s in belem),
    }


def test_transit_first_rides_medium_legs() -> None:
    # One ~2.2 km leg (1.7 km straight line x 1.3 detour): walked when walking is allowed,
    # ridden by transit-first travellers.
    stops = [stop(i, 38.70 + 0.015 * i, -9.14, "landmark") for i in range(2)]
    walk_and_ride = plan(stops, modes=ALL_MODES).days[0]
    ride = plan(stops, modes=("transit",)).days[0]
    assert walk_and_ride.transit_legs == 0
    assert ride.transit_legs == 1
    assert ride.walking_m == 0
