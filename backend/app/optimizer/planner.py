"""Turn selected stops into an optimized, scheduled multi-day walking plan.

Three ways of splitting stops into days are tried and the shortest total wins:
balanced k-means, one long tour cut into days ("route first, cluster second"), and
the selection order cut into days. Every day is then ordered by the TSP solver, seeded
with the selection order, so the plan is never longer than the selection order itself.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.optimizer.days import balanced_kmeans, split_sequence
from app.optimizer.distance import DistanceProvider, DistanceSource, Matrix
from app.optimizer.geometry import LatLon, count_self_intersections
from app.optimizer.tsp import order_stops, path_cost
from app.schemas.trip import Pace

WALKING_M_PER_MIN = 4000 / 60  # 4 km/h: Lisbon is hilly
DAY_START_MIN = 9 * 60 + 30
DAY_BUDGET_MIN: dict[Pace, int] = {"relaxed": 6 * 60, "moderate": 8 * 60, "intense": 10 * 60}
VISIT_MIN: dict[str, int] = {
    "museum": 90,
    "gallery": 60,
    "landmark": 45,
    "monument": 10,
    "viewpoint": 20,
    "religious": 25,
    "park": 40,
    "culture": 30,
    "market": 40,
    "attraction": 60,
}
DEFAULT_VISIT_MIN = 30


@dataclass(frozen=True)
class Stop:
    id: int
    lat: float
    lon: float
    category: str
    # Selection rank: 0 is the most important. Budget trimming drops the largest first.
    priority: int


@dataclass(frozen=True)
class StartPoint:
    lat: float
    lon: float
    round_trip: bool = False


@dataclass(frozen=True)
class Visit:
    stop: Stop
    walk_m: float  # from the previous stop (or the start point)
    arrive_min: int  # minutes since midnight
    leave_min: int


@dataclass(frozen=True)
class DayPlan:
    day: int
    visits: list[Visit]
    distance_m: float  # including the walk back for round trips
    total_min: int
    self_intersections: int


@dataclass(frozen=True)
class RoutePlan:
    days: list[DayPlan]
    strategy: str
    distance_source: DistanceSource
    dropped: list[Stop] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_distance_m(self) -> float:
        return sum(d.distance_m for d in self.days)

    @property
    def self_intersections(self) -> int:
        return sum(d.self_intersections for d in self.days)


def visit_minutes(category: str) -> int:
    return VISIT_MIN.get(category, DEFAULT_VISIT_MIN)


class _Problem:
    """Matrix indices: stops are 0..n-1, the start point (if any) is n."""

    def __init__(self, matrix: Matrix, stops: Sequence[Stop], start: StartPoint | None) -> None:
        self.matrix = matrix
        self.stops = stops
        self.start = len(stops) if start else None
        self.round_trip = bool(start and start.round_trip)
        self.rank = {i: stops[i].priority for i in range(len(stops))}

    def path(self, order: Sequence[int]) -> list[int]:
        prefix = [self.start] if self.start is not None else []
        suffix = [self.start] if self.start is not None and self.round_trip and order else []
        return prefix + list(order) + suffix

    def cost(self, order: Sequence[int]) -> float:
        return path_cost(self.matrix, self.path(order)) if order else 0.0

    def solve_day(self, group: Sequence[int]) -> list[int]:
        initial = sorted(group, key=lambda i: self.rank[i])
        return order_stops(
            self.matrix, group, start=self.start, round_trip=self.round_trip, initial=initial
        )


def _split_strategies(problem: _Problem, days: int) -> dict[str, list[list[int]]]:
    n = len(problem.stops)
    by_priority = sorted(range(n), key=lambda i: problem.rank[i])
    whole_tour = order_stops(problem.matrix, range(n))
    points = [LatLon(s.lat, s.lon) for s in problem.stops]
    return {
        "kmeans": balanced_kmeans(points, days),
        "route-first": split_sequence(whole_tour, days, problem.cost),
        "selection-order": split_sequence(by_priority, days, problem.cost),
    }


def _schedule(problem: _Problem, order: Sequence[int]) -> tuple[list[Visit], int]:
    visits, clock, previous = [], float(DAY_START_MIN), problem.start
    for i in order:
        walk = problem.matrix[previous][i] if previous is not None else 0.0
        clock += walk / WALKING_M_PER_MIN
        arrive = clock
        clock += visit_minutes(problem.stops[i].category)
        visits.append(Visit(problem.stops[i], walk, round(arrive), round(clock)))
        previous = i
    if problem.round_trip and order and problem.start is not None:
        clock += problem.matrix[order[-1]][problem.start] / WALKING_M_PER_MIN
    return visits, round(clock - DAY_START_MIN)


def _fit_budget(
    problem: _Problem, order: list[int], budget_min: int
) -> tuple[list[int], list[int]]:
    """Drop the least important stops until the day fits; returns (order, dropped)."""
    dropped: list[int] = []
    while len(order) > 1 and _schedule(problem, order)[1] > budget_min:
        worst = max(order, key=lambda i: problem.rank[i])
        dropped.append(worst)
        order = problem.solve_day([i for i in order if i != worst])
    return order, dropped


async def plan_route(
    stops: Sequence[Stop],
    *,
    days: int,
    pace: Pace,
    provider: DistanceProvider,
    start: StartPoint | None = None,
    enforce_budget: bool = True,
) -> RoutePlan:
    if not stops:
        raise ValueError("no stops to plan")
    warnings: list[str] = []
    if days > len(stops):
        warnings.append(f"only {len(stops)} stops for {days} days; using {len(stops)} days")
        days = len(stops)

    points = [LatLon(s.lat, s.lon) for s in stops] + (
        [LatLon(start.lat, start.lon)] if start else []
    )
    distances = await provider.matrix(points)
    problem = _Problem(distances.matrix, stops, start)

    candidates = {
        name: [problem.solve_day(group) for group in groups if group]
        for name, groups in _split_strategies(problem, days).items()
    }
    strategy, day_orders = min(
        candidates.items(), key=lambda item: sum(problem.cost(o) for o in item[1])
    )

    dropped: list[int] = []
    if enforce_budget:
        budget = DAY_BUDGET_MIN[pace]
        fitted = []
        for order in day_orders:
            order, removed = _fit_budget(problem, order, budget)
            fitted.append(order)
            dropped.extend(removed)
        day_orders = fitted
        if dropped:
            warnings.append(f"dropped {len(dropped)} stop(s) to fit {budget // 60} h days")

    # Day 1 holds the most important stop, and so on.
    day_orders.sort(key=lambda order: min(problem.rank[i] for i in order))
    plans = []
    for number, order in enumerate(day_orders, start=1):
        visits, total_min = _schedule(problem, order)
        path_points = [points[i] for i in problem.path(order)]
        if problem.round_trip:
            path_points = path_points[:-1]
        plans.append(
            DayPlan(
                day=number,
                visits=visits,
                distance_m=problem.cost(order),
                total_min=total_min,
                self_intersections=count_self_intersections(path_points, closed=problem.round_trip),
            )
        )
    return RoutePlan(
        days=plans,
        strategy=strategy,
        distance_source=distances.source,
        dropped=sorted((stops[i] for i in dropped), key=lambda s: s.priority),
        warnings=warnings,
    )
