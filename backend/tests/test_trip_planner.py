"""Turning optimizer output into the API response: map segments, rides, transit source."""

import asyncio
from datetime import date

from app.optimizer.distance import HaversineProvider
from app.optimizer.planner import ALL_MODES, DayPlan, DayWindow, Stop, Visit, plan_route
from app.optimizer.transit import TransitRoute, parse_routes
from app.schemas.plan import PlannedDay, RouteSegment
from app.services.trip_planner import (
    day_segments,
    free_evening,
    planned_stop,
    transit_ride,
    transit_source,
    window_of,
)
from tests.fakes import FakeTransit
from tests.optimizer.test_transit import fixture

STOPS = [
    Stop(1, 38.7075, -9.1364, "landmark", priority=0),  # Praca do Comercio
    Stop(2, 38.7116, -9.1301, "viewpoint", priority=1),  # Santa Luzia
    Stop(3, 38.7139, -9.1335, "landmark", priority=2),  # castle
    Stop(4, 38.6916, -9.2160, "landmark", priority=3),  # Belem Tower, 7 km away
]


def metro_and_train() -> TransitRoute:
    route = parse_routes(fixture("figueira_belem"))
    assert route is not None
    return route


def lisbon_day(route: TransitRoute | None) -> DayPlan:
    plan = asyncio.run(
        plan_route(
            STOPS,
            days=1,
            pace="intense",
            provider=HaversineProvider(),
            modes=ALL_MODES,
            transit=FakeTransit(lambda a, b: route),
        )
    )
    return plan.days[0]


def test_a_ride_is_drawn_along_its_route() -> None:
    route = metro_and_train()
    segments = asyncio.run(day_segments(lisbon_day(route), None, HaversineProvider()))
    rides = [s for s in segments if s.ride is not None]
    assert [s.ride.line for s in rides if s.ride] == ["Verde", "Linha de Cascais"]
    # The route's sections, walks to and from the stations included, replace one straight line.
    first = segments.index(rides[0]) - 1
    assert [s.mode for s in segments[first : first + 5]] == [
        "walk",
        "transit",
        "walk",
        "transit",
        "walk",
    ]
    for segment, section in zip(segments[first : first + 5], route.sections, strict=True):
        assert segment.geometry == [(p.lon, p.lat) for p in section.path]
    # The three walks between the centre stops stay one street-routed path.
    assert sum(s.mode == "walk" for s in segments) == 1 + 3


def test_an_estimated_ride_is_a_straight_line() -> None:
    segments = asyncio.run(day_segments(lisbon_day(None), None, HaversineProvider()))
    [ride] = [s for s in segments if s.mode == "transit"]
    assert ride.ride is None
    assert len(ride.geometry) == 2


def test_stop_lists_its_rides() -> None:
    route = metro_and_train()
    visit = next(v for v in lisbon_day(route).visits if v.leg and v.leg.mode == "transit")
    stop = planned_stop(visit, "Torre de Belém", None, None)
    assert (stop.travel_mode, stop.travel_min) == ("transit", 24)
    assert stop.distance_from_previous_m == round(route.distance_m)
    metro, train = stop.rides
    assert (metro.vehicle, metro.line, metro.color, metro.minutes) == (
        "metro",
        "Verde",
        "#009933",
        3,
    )
    assert (metro.board, metro.alight, metro.stops) == ("Rossio", "Cais do Sodré", 2)
    assert "Metropolitano de Lisboa" in metro.attributions[0].text
    assert (train.vehicle, train.headsign) == ("train", "Cascais")


def day_of(*segments: RouteSegment) -> PlannedDay:
    return PlannedDay(
        day=1,
        stops=[],
        distance_m=0,
        walking_m=0,
        transit_legs=0,
        duration_min=0,
        self_intersections=0,
        segments=list(segments),
    )


def test_transit_source() -> None:
    walk = RouteSegment(mode="walk", geometry=[])
    estimate = RouteSegment(mode="transit", geometry=[])
    real = RouteSegment(mode="transit", geometry=[], ride=transit_ride(metro_and_train().rides[0]))
    assert transit_source([day_of(walk)]) is None
    assert transit_source([day_of(walk, estimate)]) == "estimate"
    assert transit_source([day_of(real), day_of(walk)]) == "here"
    assert transit_source([day_of(real), day_of(estimate)]) == "mixed"


def day_until(leave_min: int, window: DayWindow) -> DayPlan:
    """A day whose last stop is left at `leave_min`."""
    visit = Visit(STOPS[0], None, leave_min - 45, leave_min)
    return DayPlan(1, [visit], None, 0, 0, 0, 45, 0, window)


def test_a_free_evening() -> None:
    overnight = DayWindow(16 * 60, 27 * 60)
    assert free_evening(day_until(21 * 60 + 40, overnight)) == "21:40"
    assert free_evening(day_until(17 * 60 + 30, DayWindow())) == "17:30"  # 09:30 to 21:30
    # Half an hour before the end is not an evening out; nor is a day that ends at 18:00.
    assert free_evening(day_until(26 * 60 + 30, overnight)) is None
    assert free_evening(day_until(15 * 60, DayWindow(9 * 60 + 30, 18 * 60))) is None


def test_saved_days_have_their_hours_and_dates() -> None:
    params = {
        "start_date": "2026-11-02",
        "windows": [[960, 1620, 420, 1056], [570, 1290, 421, 1055]],
    }
    assert window_of(params, 1) == DayWindow(960, 1620, 420, 1056, on=date(2026, 11, 2))
    assert window_of(params, 2) == DayWindow(570, 1290, 421, 1055, on=date(2026, 11, 3))
    # Plans saved before days had their own hours, or dates.
    assert window_of({"start_date": "2026-11-02"}, 1) == DayWindow(on=date(2026, 11, 2))
    assert window_of({}, 1) == DayWindow()
