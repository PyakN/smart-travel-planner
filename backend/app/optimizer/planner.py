"""Turn selected stops into an optimized, scheduled multi-day plan.

The objective is total travel time. With walking and transit allowed, legs up to
TRANSIT_MIN_DISTANCE_M are walked and longer ones (e.g. the centre to Belem) are ridden by
metro, tram, bus or train; travellers who prefer transit ride from TRANSIT_FIRST_MIN_DISTANCE_M.
Walking only makes time proportional to walking distance, so the plan is the shortest walk.

Ride times start as a fixed-speed estimate. With a transit provider, the real routes of the
legs the plan rides are then fetched and the plan is made again, until it only rides legs
with known routes (or TRANSIT_ROUNDS runs out): a handful of requests per plan instead of a
route for every pair of stops. A real route slower than walking turns the leg into a walk.

Three ways of splitting stops into days are tried and the cheapest total wins:
balanced k-means, one long tour cut into days ("route first, cluster second"), and
the selection order cut into days. Every day is then ordered by the TSP solver, seeded
with the selection order, so the plan is never worse than the selection order itself.

Weather-aware plans get the conditions of every trip day: how bad each minute is for
outdoor sights (rain, snow, fog, poor visibility, darkness). The plan is made as above,
then an outdoor visit's share of bad minutes costs up to OUTDOOR_PENALTY_MIN more minutes
of travel (soft time windows). The days are matched to the trip dates that suit them, each
day is reordered, and outdoor stops caught in bad weather move to another day, alone or in
exchange for an indoor stop, while that lowers travel time plus penalty. No day goes over
its time budget for it, and dry, light days keep the plan they had without weather.
"""

from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import accumulate, pairwise, permutations
from math import ceil, inf
from typing import Literal

from app.optimizer.days import balanced_kmeans, day_sizes, split_sequence
from app.optimizer.distance import DistanceProvider, DistanceSource, Matrix, symmetrize
from app.optimizer.geometry import LatLon, count_self_intersections
from app.optimizer.transit import TransitProvider, TransitRoute
from app.optimizer.tsp import EPS, order_stops, path_cost
from app.schemas.trip import Pace

WALKING_M_PER_MIN = 4000 / 60  # 4 km/h: Lisbon is hilly
# Longer legs use public transport: a fixed overhead (walk to the stop, wait) plus
# ~15 km/h door to door, which is typical for Lisbon's trams, metro and trains.
TRANSIT_MIN_DISTANCE_M = 2500
# Transit without walking: ride anything longer than a short stroll.
TRANSIT_FIRST_MIN_DISTANCE_M = 1000
TRANSIT_OVERHEAD_MIN = 10
TRANSIT_M_PER_MIN = 15000 / 60
# Fetch-and-replan rounds for real transit routes; plans usually settle after one or two.
TRANSIT_ROUNDS = 3
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
# An outdoor visit wholly in rain or the dark costs like this many more minutes of travel:
# worth a detour in the neighbourhood, not a trip across town.
OUTDOOR_PENALTY_MIN = 45
# Outdoor stops moved between days per plan, at most.
MAX_WEATHER_TRADES = 12


@dataclass(frozen=True)
class Stop:
    id: int
    lat: float
    lon: float
    category: str
    # Selection rank: 0 is the most important. Budget trimming drops the largest first.
    priority: int
    # Must-visit: trimmed only once a day has nothing optional left, then moved to
    # another day that can make room for it.
    required: bool = False
    # Visited in the open air: weather-aware plans keep it out of rain and darkness.
    outdoor: bool = False


@dataclass(frozen=True)
class DayConditions:
    """How unfit each minute of a trip day is for outdoor stops, from 0 (fine) to 1 (stay
    inside). Kept as running sums, so the share of a visit is a subtraction."""

    cumulative: tuple[float, ...]  # cumulative[m]: the first m minutes since midnight

    @classmethod
    def from_minutes(cls, badness: Sequence[float]) -> "DayConditions":
        if not badness:
            raise ValueError("conditions need at least one minute")
        return cls(tuple(accumulate(badness, initial=0.0)))

    def _sum_to(self, minute: float) -> float:
        last = len(self.cumulative) - 1
        m = max(0, round(minute))
        if m <= last:
            return self.cumulative[m]
        # Past the end of the day, minutes count like its last one.
        return self.cumulative[last] + (m - last) * (self.cumulative[last] - self.cumulative[-2])

    def bad_share(self, start: float, end: float) -> float:
        """Average badness of the minutes from `start` to `end`."""
        if end <= start:
            return 0.0
        return (self._sum_to(end) - self._sum_to(start)) / (end - start)


@dataclass(frozen=True)
class StartPoint:
    lat: float
    lon: float
    round_trip: bool = False


TravelMode = Literal["walk", "transit"]
ALL_MODES: tuple[TravelMode, ...] = ("walk", "transit")


@dataclass(frozen=True)
class Leg:
    mode: TravelMode
    distance_m: float  # on foot for walks; walks plus rides for real transit routes
    minutes: float
    # The public transport route of a ridden leg; None for walks and estimated rides.
    route: TransitRoute | None = None

    @property
    def walking_m(self) -> float:
        if self.mode == "walk":
            return self.distance_m
        return self.route.walking_m if self.route else 0.0


def transit_threshold_m(modes: Collection[TravelMode]) -> float:
    """Legs longer than this are ridden; `inf` when the traveller only walks."""
    if not modes:
        raise ValueError("at least one travel mode is needed")
    if "transit" not in modes:
        return inf
    return TRANSIT_MIN_DISTANCE_M if "walk" in modes else TRANSIT_FIRST_MIN_DISTANCE_M


def travel_leg(
    distance_m: float,
    transit_from_m: float = TRANSIT_MIN_DISTANCE_M,
    route: TransitRoute | None = None,
    *,
    walking: bool = True,
) -> Leg:
    """Walk legs up to `transit_from_m`, ride longer ones.

    Without a real `route` the ride is estimated from the distance. With one, the leg is
    walked when the route rides nothing, or when walking is faster and the traveller walks.
    """
    walk = Leg("walk", distance_m, distance_m / WALKING_M_PER_MIN)
    if distance_m <= transit_from_m:
        return walk
    if route is None:
        minutes = TRANSIT_OVERHEAD_MIN + distance_m / TRANSIT_M_PER_MIN
        return Leg("transit", distance_m, minutes)
    if not route.rides or (walking and walk.minutes <= route.minutes):
        return walk
    return Leg("transit", route.distance_m, route.minutes, route)


@dataclass(frozen=True)
class Visit:
    stop: Stop
    leg: Leg | None  # from the previous stop or the start point; None for a free start
    arrive_min: int  # minutes since midnight
    leave_min: int


@dataclass(frozen=True)
class DayPlan:
    day: int
    visits: list[Visit]
    return_leg: Leg | None  # back to the start point on round trips
    distance_m: float  # all legs, including the way back for round trips
    walking_m: float
    transit_legs: int
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


def day_hours(pace: Pace) -> tuple[int, int]:
    """The sightseeing hours of a day at this pace, in minutes since midnight."""
    return DAY_START_MIN, DAY_START_MIN + DAY_BUDGET_MIN[pace]


Routes = Mapping[tuple[int, int], TransitRoute | None]


@dataclass(frozen=True)
class _DayCost:
    travel: float  # minutes, each leg in its own direction
    bad: float  # outdoor visits' average badness, summed
    length: int  # minutes from the start of the day to its end, as _schedule counts them

    @property
    def total(self) -> float:
        return self.travel + OUTDOOR_PENALTY_MIN * self.bad


class _Problem:
    """Matrix indices: stops are 0..n-1, the start point (if any) is n.

    `legs[a][b]` is how to get from a to b and `distance` is in metres on foot. `matrix`
    holds the travel minutes the solvers minimise, averaged over both directions (they
    need it symmetric). `routes` are the transit routes fetched so far, by (from, to).
    `conditions` are the weather of the trip days, in date order, for weather-aware plans.
    """

    def __init__(
        self,
        distance: Matrix,
        stops: Sequence[Stop],
        start: StartPoint | None,
        modes: Collection[TravelMode],
        routes: Routes,
        conditions: Sequence[DayConditions] | None = None,
    ) -> None:
        self.distance = distance
        self.transit_from_m = transit_threshold_m(modes)
        self.routes = routes
        walking = "walk" in modes
        n = len(distance)
        self.legs = [[self._leg(a, b, walking) for b in range(n)] for a in range(n)]
        self.matrix = symmetrize([[leg.minutes for leg in row] for row in self.legs])
        self.stops = stops
        self.start = len(stops) if start else None
        self.round_trip = bool(start and start.round_trip)
        self.rank = {i: stops[i].priority for i in range(len(stops))}
        self.conditions = conditions
        self.visit_min = [visit_minutes(s.category) for s in stops]

    def _leg(self, a: int, b: int, walking: bool) -> Leg:
        d = self.distance[a][b]
        if (a, b) in self.routes:
            return travel_leg(d, self.transit_from_m, self.routes[a, b], walking=walking)
        if (b, a) in self.routes:
            # The way back is a good guess for the time until this direction is fetched.
            guess = travel_leg(d, self.transit_from_m, self.routes[b, a], walking=walking)
            return replace(guess, route=None)
        return travel_leg(d, self.transit_from_m)

    def unknown_rides(self, day_orders: Sequence[Sequence[int]]) -> list[tuple[int, int]]:
        """Legs of the plan long enough to ride whose route has not been asked for yet."""
        legs = (leg for order in day_orders for leg in pairwise(self.path(order)))
        return [
            (a, b)
            for a, b in dict.fromkeys(legs)
            if self.distance[a][b] > self.transit_from_m and (a, b) not in self.routes
        ]

    def path(self, order: Sequence[int]) -> list[int]:
        prefix = [self.start] if self.start is not None else []
        suffix = [self.start] if self.start is not None and self.round_trip and order else []
        return prefix + list(order) + suffix

    def cost(self, order: Sequence[int]) -> float:
        """Travel minutes for a day in this order."""
        return path_cost(self.matrix, self.path(order)) if order else 0.0

    def day_legs(self, order: Sequence[int]) -> list[Leg]:
        path = self.path(order)
        return [self.legs[a][b] for a, b in zip(path, path[1:], strict=False)]

    def solve_day(self, group: Sequence[int]) -> list[int]:
        initial = sorted(group, key=lambda i: self.rank[i])
        return order_stops(
            self.matrix, group, start=self.start, round_trip=self.round_trip, initial=initial
        )

    def weather_cost(self, order: Sequence[int], day: int) -> _DayCost:
        """Travel and weather of a day in this order on trip day `day` (0 is the first).

        The schedule is _schedule's; this is the lean version local search calls a lot.
        """
        conditions = self.conditions[day] if self.conditions else None
        clock, travel, bad = float(DAY_START_MIN), 0.0, 0.0
        previous = self.start
        for i in order:
            if previous is not None:
                minutes = self.legs[previous][i].minutes
                clock += minutes
                travel += minutes
            leave = clock + self.visit_min[i]
            if conditions is not None and self.stops[i].outdoor:
                bad += conditions.bad_share(clock, leave)
            clock, previous = leave, i
        if self.round_trip and order and self.start is not None:
            minutes = self.legs[order[-1]][self.start].minutes
            clock += minutes
            travel += minutes
        return _DayCost(travel, bad, round(clock - DAY_START_MIN))

    def exposed(self, order: Sequence[int], day: int) -> list[int]:
        """Outdoor stops of a day that meet bad weather or darkness."""
        if not self.conditions:
            return []
        conditions = self.conditions[day]
        visits = _schedule(self, order)[0]
        return [
            i
            for i, v in zip(order, visits, strict=True)
            if v.stop.outdoor and conditions.bad_share(v.arrive_min, v.leave_min) > EPS
        ]


def _split_by_time(
    problem: _Problem, sequence: Sequence[int], days: int, budget_min: int
) -> list[list[int]]:
    """Contiguous days that each fit the time budget, sizes free down to half the average.

    Dense areas can then fill a day while spread-out ones take fewer stops. Falls back
    to equal-size days when no split fits the budget (trimming deals with it later).
    """

    def day_cost(chunk: Sequence[int]) -> float:
        fits = _schedule(problem, chunk)[1] <= budget_min
        return problem.cost(chunk) if fits else inf

    min_size = ceil(day_sizes(len(sequence), days)[0] / 2)
    split = split_sequence(sequence, days, day_cost, min_size=min_size, max_size=len(sequence))
    if split is None:
        split = split_sequence(sequence, days, problem.cost)
    assert split is not None  # balanced split is always feasible
    return split


def _split_strategies(problem: _Problem, days: int, budget_min: int) -> dict[str, list[list[int]]]:
    n = len(problem.stops)
    by_priority = sorted(range(n), key=lambda i: problem.rank[i])
    whole_tour = order_stops(problem.matrix, range(n))
    points = [LatLon(s.lat, s.lon) for s in problem.stops]
    return {
        "kmeans": balanced_kmeans(points, days),
        "route-first": _split_by_time(problem, whole_tour, days, budget_min),
        "selection-order": _split_by_time(problem, by_priority, days, budget_min),
    }


def _schedule(problem: _Problem, order: Sequence[int]) -> tuple[list[Visit], int]:
    visits: list[Visit] = []
    clock, previous = float(DAY_START_MIN), problem.start
    for i in order:
        leg = problem.legs[previous][i] if previous is not None else None
        clock += leg.minutes if leg else 0.0
        arrive = clock
        clock += visit_minutes(problem.stops[i].category)
        visits.append(Visit(problem.stops[i], leg, round(arrive), round(clock)))
        previous = i
    if problem.round_trip and order and problem.start is not None:
        clock += problem.legs[order[-1]][problem.start].minutes
    return visits, round(clock - DAY_START_MIN)


def _fit_budget(
    problem: _Problem, order: list[int], budget_min: int
) -> tuple[list[int], list[int]]:
    """Drop the least important stops until the day fits; returns (order, dropped).

    Optional stops go first; must-visit ones only when nothing optional is left.
    """
    dropped: list[int] = []
    while len(order) > 1 and _schedule(problem, order)[1] > budget_min:
        worst = max(order, key=lambda i: (not problem.stops[i].required, problem.rank[i]))
        dropped.append(worst)
        order = problem.solve_day([i for i in order if i != worst])
    return order, dropped


def _make_room(
    problem: _Problem, order: Sequence[int], stop: int, budget_min: int
) -> tuple[list[int], list[int]] | None:
    """Add `stop` to a day, dropping its least important optional stops until it fits."""
    new_order = problem.solve_day([*order, stop])
    removed: list[int] = []
    while _schedule(problem, new_order)[1] > budget_min:
        optional = [i for i in new_order if not problem.stops[i].required]
        if not optional:
            return None
        worst = max(optional, key=lambda i: problem.rank[i])
        removed.append(worst)
        new_order = problem.solve_day([i for i in new_order if i != worst])
    return new_order, removed


def _place_required(
    problem: _Problem, day_orders: list[list[int]], dropped: list[int], budget_min: int
) -> list[int]:
    """Give each dropped must-visit stop the day that loses the fewest optional stops for it.

    Updates `day_orders` in place; returns the new dropped list.
    """
    dropped = list(dropped)
    for stop in sorted(
        (i for i in dropped if problem.stops[i].required), key=lambda i: problem.rank[i]
    ):
        options = []
        for d, order in enumerate(day_orders):
            placed = _make_room(problem, order, stop, budget_min)
            if placed is not None:
                new_order, removed = placed
                added = problem.cost(new_order) - problem.cost(order)
                options.append((len(removed), added, d, new_order, removed))
        if options:
            _, _, d, new_order, removed = min(options, key=lambda o: (o[0], o[1], o[2]))
            day_orders[d] = new_order
            dropped.remove(stop)
            dropped.extend(removed)
    return dropped


def _cheapest_insertion(problem: _Problem, order: Sequence[int], stop: int) -> float:
    base = problem.cost(order)
    return min(
        problem.cost([*order[:pos], stop, *order[pos:]]) - base for pos in range(len(order) + 1)
    )


def _rebalance(problem: _Problem, day_orders: list[list[int]], budget_min: int) -> list[list[int]]:
    """Move stops between days while that cuts total travel time and every day fits.

    The initial splits keep days equal in stop count; real days are limited by time, so a
    dense neighbourhood can take more stops than a spread-out one.
    """
    days = [list(order) for order in day_orders]
    duration = [_schedule(problem, order)[1] for order in days]
    improved = True
    while improved:
        improved = False
        for a in range(len(days)):
            for stop in list(days[a]):
                if len(days[a]) <= 1:
                    break
                without = [i for i in days[a] if i != stop]
                gain = problem.cost(days[a]) - problem.cost(without)
                for b in range(len(days)):
                    # Cheap filter first, then re-solve both days and check exactly.
                    if b == a or _cheapest_insertion(problem, days[b], stop) >= gain - EPS:
                        continue
                    new_a, new_b = problem.solve_day(without), problem.solve_day([*days[b], stop])
                    dur_a, dur_b = _schedule(problem, new_a)[1], _schedule(problem, new_b)[1]
                    if dur_b > budget_min or dur_a > max(budget_min, duration[a]):
                        continue
                    old = problem.cost(days[a]) + problem.cost(days[b])
                    if problem.cost(new_a) + problem.cost(new_b) < old - EPS:
                        days[a], days[b] = new_a, new_b
                        duration[a], duration[b] = dur_a, dur_b
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return days


def _reorderings(order: Sequence[int]) -> Iterator[list[int]]:
    """Orders one move away: a stop moved elsewhere, two stops swapped, a run reversed."""
    n = len(order)
    for i in range(n):
        rest = [*order[:i], *order[i + 1 :]]
        for j in range(n):
            if j != i:
                yield [*rest[:j], order[i], *rest[j:]]
    for i in range(n):
        for j in range(i + 1, n):
            swapped = list(order)
            swapped[i], swapped[j] = swapped[j], swapped[i]
            yield swapped
    for i in range(n):
        for j in range(i + 3, n + 1):  # runs of two are swaps
            yield [*order[:i], *reversed(order[i:j]), *order[j:]]


def _improve_day(problem: _Problem, order: Sequence[int], day: int, limit: int) -> list[int]:
    """First-improvement local search for travel plus weather, within `limit` minutes."""
    best = list(order)
    best_cost = problem.weather_cost(best, day).total
    improved = True
    while improved:
        improved = False
        for candidate in _reorderings(best):
            cost = problem.weather_cost(candidate, day)
            if cost.total < best_cost - EPS and cost.length <= limit:
                best, best_cost, improved = candidate, cost.total, True
                break
    return best


def _weather_order(problem: _Problem, order: Sequence[int], day: int, budget: int) -> list[int]:
    """Reorder a day so its outdoor stops meet less bad weather, if any of them meets some.

    The day keeps to the budget (or to its current length, if that is longer already).
    Also tried from the reversed order: a day often just needs turning around.
    """
    current = problem.weather_cost(order, day)
    if current.bad <= EPS:
        return list(order)
    limit = max(budget, current.length)
    seeds = [list(order)]
    if problem.weather_cost(order[::-1], day).length <= limit:
        seeds.append(list(order[::-1]))
    improved = [_improve_day(problem, seed, day, limit) for seed in seeds]
    return min(improved, key=lambda o: problem.weather_cost(o, day).total)


def _assign_dates(problem: _Problem, day_orders: list[list[int]]) -> list[list[int]]:
    """Put each day's stops on the trip date where they meet the least bad weather.

    Every assignment is tried (7! for a week). Unless one is better, days keep their
    order, so day 1 still holds the most important stop.
    """
    n = len(day_orders)
    cost = [
        [
            min(problem.weather_cost(o, d).total, problem.weather_cost(o[::-1], d).total)
            for d in range(n)
        ]
        for o in day_orders
    ]

    def total(dates: Sequence[int]) -> float:
        return sum(cost[i][d] for i, d in enumerate(dates))

    keep = tuple(range(n))
    best = min(permutations(keep), key=total)
    if total(best) >= total(keep) - EPS:
        return day_orders
    dated: list[list[int]] = [[] for _ in range(n)]
    for i, d in enumerate(best):
        dated[d] = day_orders[i]
    return dated


def _best_insertion(
    problem: _Problem, order: Sequence[int], stop: int, day: int, limit: int
) -> list[int] | None:
    """`order` with `stop` where it costs the least on trip day `day`, within `limit`."""
    options = []
    for pos in range(len(order) + 1):
        new = [*order[:pos], stop, *order[pos:]]
        cost = problem.weather_cost(new, day)
        if cost.length <= limit:
            options.append((cost.total, pos, new))
    return min(options)[2] if options else None


def _trades(
    problem: _Problem, days: list[list[int]], limits: Sequence[int]
) -> Iterator[tuple[int, int, list[int], list[int]]]:
    """(a, b, new day a, new day b): an outdoor stop of day a that meets bad weather moves
    to day b, alone or in exchange for one of b's indoor stops. Both days fit their limits."""
    for a, order in enumerate(days):
        for stop in problem.exposed(order, a):
            without = [i for i in order if i != stop]
            for b, other in enumerate(days):
                if b == a:
                    continue
                if without and problem.weather_cost(without, a).length <= limits[a]:
                    moved = _best_insertion(problem, other, stop, b, limits[b])
                    if moved is not None:
                        yield a, b, without, moved
                for indoor in (i for i in other if not problem.stops[i].outdoor):
                    into_a = _best_insertion(problem, without, indoor, a, limits[a])
                    rest = [i for i in other if i != indoor]
                    into_b = _best_insertion(problem, rest, stop, b, limits[b])
                    if into_a is not None and into_b is not None:
                        yield a, b, into_a, into_b


def _trade_days(problem: _Problem, day_orders: list[list[int]], budget: int) -> list[list[int]]:
    """Make the best trade of outdoor stops between days while one lowers travel time plus
    weather penalty, then reorder the two days it changed."""
    days = [list(order) for order in day_orders]
    for _ in range(MAX_WEATHER_TRADES):
        costs = [problem.weather_cost(order, d) for d, order in enumerate(days)]
        limits = [max(budget, cost.length) for cost in costs]
        best_gain, best = EPS, None
        for a, b, new_a, new_b in _trades(problem, days, limits):
            after = problem.weather_cost(new_a, a).total + problem.weather_cost(new_b, b).total
            gain = costs[a].total + costs[b].total - after
            if gain > best_gain:
                best_gain, best = gain, (a, b, new_a, new_b)
        if best is None:
            break
        a, b, new_a, new_b = best
        days[a] = _weather_order(problem, new_a, a, limits[a])
        days[b] = _weather_order(problem, new_b, b, limits[b])
    return days


def _weather_schedule(
    problem: _Problem, day_orders: list[list[int]], budget: int
) -> list[list[int]]:
    """Days on the dates that suit them, each day reordered, then trades between days."""
    dated = _assign_dates(problem, day_orders)
    dated = [_weather_order(problem, order, d, budget) for d, order in enumerate(dated)]
    return _trade_days(problem, dated, budget)


@dataclass(frozen=True)
class _Solution:
    strategy: str
    day_orders: list[list[int]]
    dropped: list[int]
    warnings: list[str]


def _solve(problem: _Problem, days: int, budget: int, enforce_budget: bool) -> _Solution:
    candidates = {
        name: [problem.solve_day(group) for group in groups if group]
        for name, groups in _split_strategies(problem, days, budget).items()
    }
    strategy, day_orders = min(
        candidates.items(), key=lambda item: sum(problem.cost(o) for o in item[1])
    )
    day_orders = _rebalance(problem, day_orders, budget)

    dropped: list[int] = []
    warnings: list[str] = []
    if enforce_budget:
        fitted = []
        for order in day_orders:
            order, removed = _fit_budget(problem, order, budget)
            fitted.append(order)
            dropped.extend(removed)
        day_orders = fitted
        dropped = _place_required(problem, day_orders, dropped, budget)
        if dropped:
            warnings.append(f"dropped {len(dropped)} stop(s) to fit {budget // 60} h days")
        if missed := sum(problem.stops[i].required for i in dropped):
            warnings.append(f"{missed} must-visit stop(s) do not fit any day")

    # Day 1 holds the most important stop, and so on, unless the weather says otherwise.
    day_orders.sort(key=lambda order: min(problem.rank[i] for i in order))
    if problem.conditions is not None:
        day_orders = _weather_schedule(problem, day_orders, budget)
    return _Solution(strategy, day_orders, dropped, warnings)


async def plan_route(
    stops: Sequence[Stop],
    *,
    days: int,
    pace: Pace,
    provider: DistanceProvider,
    start: StartPoint | None = None,
    enforce_budget: bool = True,
    modes: Collection[TravelMode] = ALL_MODES,
    transit: TransitProvider | None = None,
    conditions: Sequence[DayConditions] | None = None,
) -> RoutePlan:
    """`conditions`, one per trip day in date order, make the plan weather-aware: plan day
    N is then trip day N."""
    if not stops:
        raise ValueError("no stops to plan")
    transit_threshold_m(modes)  # fail on no modes before any routing request
    if conditions is not None and len(conditions) < days:
        raise ValueError(f"weather conditions for {len(conditions)} of {days} days")
    warnings: list[str] = []
    if days > len(stops):
        warnings.append(f"only {len(stops)} stops for {days} days; using {len(stops)} days")
        days = len(stops)

    points = [LatLon(s.lat, s.lon) for s in stops] + (
        [LatLon(start.lat, start.lon)] if start else []
    )
    distances = await provider.matrix(points)
    budget = DAY_BUDGET_MIN[pace]

    routes: dict[tuple[int, int], TransitRoute | None] = {}
    for attempt in range(TRANSIT_ROUNDS + 1):
        problem = _Problem(distances.matrix, stops, start, modes, routes, conditions)
        solution = _solve(problem, days, budget, enforce_budget)
        if transit is None or attempt == TRANSIT_ROUNDS:
            break
        unknown = problem.unknown_rides(solution.day_orders)
        if not unknown:
            break
        found = await transit.routes([(points[a], points[b]) for a, b in unknown])
        routes.update(zip(unknown, found, strict=True))

    strategy, day_orders, dropped = solution.strategy, solution.day_orders, solution.dropped
    warnings += solution.warnings
    plans = []
    for number, order in enumerate(day_orders, start=1):
        visits, total_min = _schedule(problem, order)
        legs = problem.day_legs(order)
        path_points = [points[i] for i in problem.path(order)]
        if problem.round_trip:
            path_points = path_points[:-1]
        plans.append(
            DayPlan(
                day=number,
                visits=visits,
                return_leg=legs[-1] if problem.round_trip else None,
                distance_m=sum(leg.distance_m for leg in legs),
                walking_m=sum(leg.walking_m for leg in legs),
                transit_legs=sum(leg.mode == "transit" for leg in legs),
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
