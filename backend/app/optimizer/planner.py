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

Every trip day has its hours (DayWindow): from when to when, past midnight if need be, and
its daylight. The pace is a share of those hours, so the default 09:30 to 21:30 day plans as
it always did and a day that starts at 16:00 holds less; days with shorter hours get fewer
stops when the trip is split. Stops have visit hours (app.catalog.visit_hours), which make
this a routing problem with time windows: indoor sights close and evening places open at
NIGHT_START_MIN, and outdoor sights need daylight. A visit that comes too early waits for
the place to open (free time before it), and none may run past closing time or sunset: a
day that breaks that is reordered by local search, and if that is not enough, its least
important stop with such hours is dropped.

Weather-aware plans get the conditions of every trip day: how bad each minute is for
outdoor sights (rain, snow, fog, poor visibility). The plan is made as above, then an
outdoor visit's share of bad minutes costs up to OUTDOOR_PENALTY_MIN more minutes of travel
(soft time windows). The days are matched to the trip dates that suit them, each day is
reordered, and outdoor stops caught in bad weather move to another day, alone or in
exchange for an indoor stop, while that lowers travel time plus penalty. No day goes over
its time budget for it, and dry days keep the plan they had without weather.

A day of a trip can also be re-planned as it goes (replan_day). Its visited stops stay first,
in their order; the rest begins where the traveller is, at the time given, visits one stop
first if asked, and ends back at the hotel on round trips (a path to another end). The pace
no longer limits it, only the end of the day's hours plus REPLAN_GRACE_MIN: stops are dropped
only when the day would really run long (or reach them closed or dark), least important
first, and never the ones the traveller asked for.
"""

from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import accumulate, pairwise, permutations
from math import ceil, floor, inf
from typing import Literal

from app.catalog import VisitHours
from app.optimizer.days import balanced_kmeans, split_sequence
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
MINUTES_PER_DAY = 24 * 60
DAY_START_MIN = 9 * 60 + 30
DAY_END_MIN = 21 * 60 + 30
# The pace's sightseeing time (travel and visits) in a day of the default hours, 09:30 to
# 21:30. Days with other hours get the same share of theirs: two thirds at a moderate pace;
# the rest is for meals and rest.
FULL_DAY_MIN = DAY_END_MIN - DAY_START_MIN
DAY_BUDGET_MIN: dict[Pace, int] = {"relaxed": 6 * 60, "moderate": 8 * 60, "intense": 10 * 60}
# Indoor sights close, and bars, fado houses and restaurants open, at 20:00.
NIGHT_START_MIN = 20 * 60
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
    "nightlife": 60,
    "restaurant": 90,  # dinner, or fado with it
}
DEFAULT_VISIT_MIN = 30
# An outdoor visit wholly in rain costs like this many more minutes of travel: worth a
# detour in the neighbourhood, not a trip across town.
OUTDOOR_PENALTY_MIN = 45
# Each minute a visit runs past closing time or sunset costs like this many minutes of
# travel, so local search gets rid of it first.
LATE_PENALTY_MIN = 100
# Outdoor stops moved between days per plan, at most.
MAX_WEATHER_TRADES = 12
# A re-planned day may run this long past the end of its hours before stops are dropped.
REPLAN_GRACE_MIN = 30


class NothingFitsError(ValueError):
    """None of the stops can be visited in the days' hours."""


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
    # Visited in the open air: weather-aware plans keep it out of the rain.
    outdoor: bool = False
    # When it can be visited: any time, by day (until NIGHT_START_MIN), in daylight, or at
    # night (from NIGHT_START_MIN).
    hours: VisitHours = "any"
    # Minutes there, if the traveller chose; else the visit its category takes (VISIT_MIN).
    stay_min: int | None = None


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
class DayWindow:
    """A trip day's hours in minutes since its midnight; `end_min` is past 24 * 60 when the
    day ends after midnight. Outdoor sights that need daylight are visited between sunrise
    and sunset, when those are known."""

    start_min: int = DAY_START_MIN
    end_min: int = DAY_END_MIN
    sunrise_min: int | None = None
    sunset_min: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.start_min < self.end_min <= self.start_min + MINUTES_PER_DAY:
            raise ValueError(f"no such day hours: {self.start_min} to {self.end_min}")

    @property
    def length_min(self) -> int:
        return self.end_min - self.start_min

    def budget(self, pace: Pace) -> int:
        """Minutes of travel and visits at this pace: its share of the day's hours."""
        return round(DAY_BUDGET_MIN[pace] * self.length_min / FULL_DAY_MIN)

    def opening(self, hours: VisitHours) -> tuple[float, float]:
        """When a visit with these hours may begin, and by when it must end."""
        if hours == "day":
            return -inf, NIGHT_START_MIN
        if hours == "night":
            return NIGHT_START_MIN, inf
        if hours == "daylight" and self.sunrise_min is not None and self.sunset_min is not None:
            return self.sunrise_min, self.sunset_min
        return -inf, inf


@dataclass(frozen=True)
class StartPoint:
    lat: float
    lon: float
    round_trip: bool = False


@dataclass(frozen=True)
class Origin:
    """Where the rest of a re-planned day begins (the traveller's location), and when, in
    minutes since the day's midnight; None: when it would begin anyway (where the visited
    stops end, or as the day starts)."""

    lat: float
    lon: float
    minute: int | None = None


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
    # Free time before setting off for it: the place opens later.
    wait_min: int = 0
    # Where its leg starts when not at the previous stop: the origin of a re-planned day.
    origin: Origin | None = None


@dataclass(frozen=True)
class DayPlan:
    day: int
    visits: list[Visit]
    return_leg: Leg | None  # back to the start point on round trips
    distance_m: float  # all legs, including the way back for round trips
    walking_m: float
    transit_legs: int
    total_min: int  # counted against the day's budget, as _DayCost.length
    self_intersections: int
    window: DayWindow


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


def duration_label(minutes: int) -> str:
    """Minutes as "6 h" or "3 h 40 min"."""
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


Routes = Mapping[tuple[int, int], TransitRoute | None]


@dataclass(frozen=True)
class _DayCost:
    travel: float  # minutes, each leg in its own direction
    bad: float  # outdoor visits' average bad weather, summed
    # The day against its budget: its travel and visits, or (if more) how long it runs from
    # the start of its hours less the time they leave for meals and rest. Within the budget,
    # the day keeps to the pace and ends by the end of its hours.
    length: int
    late: int  # minutes visits run past closing time or sunset

    @property
    def total(self) -> float:
        return self.travel + OUTDOOR_PENALTY_MIN * self.bad + LATE_PENALTY_MIN * self.late


class _Problem:
    """Matrix indices: stops are 0..n-1, then the points days start or end at, if any.

    Every day begins at node `start` (None: at its first stop) when its hours begin, and
    ends at node `end` (None: at its last stop; `start` itself on round trips). `first`, a
    stop, comes first on any day that has it; `protected` stops are never dropped.
    `legs[a][b]` is how to get from a to b and `distance` is in metres on foot. `matrix`
    holds the travel minutes the solvers minimise, averaged over both directions (they
    need it symmetric). `routes` are the transit routes fetched so far, by (from, to).
    `windows` are the hours of the trip days in date order, `budgets` the minutes of travel
    and visits each may take, and `conditions` their weather, for weather-aware plans; `day`
    arguments index them (0 is the first trip day).
    """

    def __init__(
        self,
        distance: Matrix,
        stops: Sequence[Stop],
        *,
        start: int | None,
        end: int | None,
        modes: Collection[TravelMode],
        routes: Routes,
        windows: Sequence[DayWindow],
        budgets: Sequence[int],
        conditions: Sequence[DayConditions] | None = None,
        first: int | None = None,
        protected: Collection[int] = (),
    ) -> None:
        self.distance = distance
        self.transit_from_m = transit_threshold_m(modes)
        self.routes = routes
        walking = "walk" in modes
        n = len(distance)
        self.legs = [[self._leg(a, b, walking) for b in range(n)] for a in range(n)]
        self.matrix = symmetrize([[leg.minutes for leg in row] for row in self.legs])
        self.stops = stops
        self.start = start
        self.end = end
        self.round_trip = end is not None and end == start
        self.first = first
        self.protected = frozenset(protected)
        self.rank = {i: stops[i].priority for i in range(len(stops))}
        self.conditions = conditions
        self.visit_min = [s.stay_min or visit_minutes(s.category) for s in stops]
        self.windows = list(windows)
        self.budgets = list(budgets)
        # opening[day][i]: when stop i may be visited that day, as DayWindow.opening.
        self.opening = [[w.opening(s.hours) for s in stops] for w in self.windows]
        self.timed = any(o != (-inf, inf) for day in self.opening for o in day)
        # Days with the same hours can take each other's stops as they are.
        self.uniform = len({(w.start_min, w.end_min) for w in self.windows}) == 1

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
        suffix = [self.end] if self.end is not None and order else []
        return prefix + list(order) + suffix

    def cost(self, order: Sequence[int]) -> float:
        """Travel minutes for a day in this order."""
        return path_cost(self.matrix, self.path(order)) if order else 0.0

    def day_legs(self, order: Sequence[int]) -> list[Leg]:
        path = self.path(order)
        return [self.legs[a][b] for a, b in zip(path, path[1:], strict=False)]

    def solve_day(self, group: Sequence[int], day: int) -> list[int]:
        """The shortest order of a day's stops that keeps to their opening hours, if any
        does: the TSP order (from the first stop, if the day has it), reordered when a visit
        runs late (weather aside)."""
        if not group:
            return []
        initial = sorted(group, key=lambda i: self.rank[i])
        first = self.first
        if first is not None and first in group:
            rest = [i for i in initial if i != first]
            path = order_stops(self.matrix, rest, start=first, end=self.end, initial=rest)
            order = [first, *path]
        else:
            order = order_stops(self.matrix, group, start=self.start, end=self.end, initial=initial)
        if self.timed and self.day_cost(order, day, weather=False).late:
            order = _reorder(self, order, day, weather=False)
        return order

    def fixed(self, order: Sequence[int]) -> int:
        """How many stops at the head of `order` keep their place: the first stop, if any."""
        return int(bool(order) and order[0] == self.first)

    def day_cost(
        self,
        order: Sequence[int],
        day: int,
        *,
        weather: bool = True,
        visits: list[Visit] | None = None,
    ) -> _DayCost:
        """Travel, weather and timing of a day in this order on trip day `day`; `visits`, if
        given, collects its schedule. Local search calls this a lot, so it stays lean."""
        window, opening = self.windows[day], self.opening[day]
        conditions = self.conditions[day] if weather and self.conditions else None
        clock = float(window.start_min)
        travel = visiting = bad = 0.0
        late = 0
        previous = self.start
        for i in order:
            leg = self.legs[previous][i] if previous is not None else None
            if leg is not None:
                clock += leg.minutes
                travel += leg.minutes
            opens, closes = opening[i]
            begin = max(clock, opens)  # wait for it to open
            leave = begin + self.visit_min[i]
            visiting += self.visit_min[i]
            if leave > closes:
                late += round(leave - closes)
            if conditions is not None and self.stops[i].outdoor:
                bad += conditions.bad_share(begin, leave)
            if visits is not None:
                # A day with a free start simply begins at its first stop.
                wait = round(begin - clock) if previous is not None else 0
                visits.append(Visit(self.stops[i], leg, round(begin), round(leave), wait))
            clock, previous = leave, i
        if self.end is not None and order:
            minutes = self.legs[order[-1]][self.end].minutes
            clock += minutes
            travel += minutes
        slack = window.length_min - self.budgets[day]
        length = max(travel + visiting, clock - window.start_min - slack)
        return _DayCost(travel, bad, round(length), late)

    def schedule(self, order: Sequence[int], day: int) -> tuple[list[Visit], _DayCost]:
        visits: list[Visit] = []
        cost = self.day_cost(order, day, visits=visits)
        return visits, cost

    def fits(self, cost: _DayCost, day: int) -> bool:
        return cost.late == 0 and cost.length <= self.budgets[day]

    def hopeless(self, i: int, day: int) -> bool:
        """Whether stop i cannot be visited at all within trip day `day`'s hours."""
        window = self.windows[day]
        opens, closes = self.opening[day][i]
        return max(opens, window.start_min) + self.visit_min[i] > min(closes, window.end_min)

    def timed_stops(self, order: Sequence[int], day: int) -> list[int]:
        """Stops of `order` that close (or lose the light) during trip day `day`; only those
        that cannot be visited that day at all, if there are any."""
        hopeless = [i for i in order if self.hopeless(i, day)]
        return hopeless or [i for i in order if self.opening[day][i][1] < inf]

    def exposed(self, order: Sequence[int], day: int) -> list[int]:
        """Outdoor stops of a day that meet bad weather."""
        if not self.conditions:
            return []
        conditions = self.conditions[day]
        visits = self.schedule(order, day)[0]
        return [
            i
            for i, v in zip(order, visits, strict=True)
            if v.stop.outdoor and conditions.bad_share(v.arrive_min, v.leave_min) > EPS
        ]


def _split_by_time(problem: _Problem, sequence: Sequence[int], days: int) -> list[list[int]]:
    """Contiguous days that each fit their time budget, sizes free down to half of what the
    shortest day would hold by its share of the budgets.

    Dense areas can then fill a day while spread-out ones take fewer stops. Falls back
    to equal-size days when no split fits the budgets (trimming deals with it later).
    """
    budgets = problem.budgets[:days]

    def day_cost(chunk: Sequence[int], day: int) -> float:
        fits = problem.day_cost(chunk, day, weather=False).length <= budgets[day]
        return problem.cost(chunk) if fits else inf

    smallest = floor(len(sequence) * min(budgets) / sum(budgets))
    min_size = ceil(smallest / 2)
    split = split_sequence(sequence, days, day_cost, min_size=min_size, max_size=len(sequence))
    if split is None:
        split = split_sequence(sequence, days, lambda chunk, _: problem.cost(chunk))
    assert split is not None  # balanced split is always feasible
    return split


def _capacities(problem: _Problem, days: int) -> list[int] | None:
    """Stops per day for k-means, by each day's share of the budgets; None if all are equal."""
    budgets = problem.budgets[:days]
    if len(set(budgets)) == 1:
        return None
    n = len(problem.stops)
    return [ceil(n * budget / sum(budgets)) for budget in budgets]


def _split_strategies(problem: _Problem, days: int) -> dict[str, list[list[int]]]:
    n = len(problem.stops)
    by_priority = sorted(range(n), key=lambda i: problem.rank[i])
    whole_tour = order_stops(problem.matrix, range(n))
    points = [LatLon(s.lat, s.lon) for s in problem.stops]
    return {
        "kmeans": balanced_kmeans(points, days, _capacities(problem, days)),
        "route-first": _split_by_time(problem, whole_tour, days),
        "selection-order": _split_by_time(problem, by_priority, days),
    }


def _fit_budget(
    problem: _Problem, order: list[int], day: int, *, shorten: bool = False
) -> tuple[list[int], list[int], list[int]]:
    """Drop stops until the day fits; returns (order, dropped for time, dropped for hours).

    While a visit runs past closing time or sunset, the least important stop with such hours
    goes (one that cannot be visited that day at all first); while the day is too long, the
    least important stop. Optional stops go first, must-visit ones only when nothing
    optional is left; protected ones never do. With `shorten`, a stop is dropped for time
    only if the day is shorter without it: an afternoon sight stays when the evening runs
    long, as the evening would wait for the bars to open anyway.
    """
    over: list[int] = []
    closed: list[int] = []
    while order:
        cost = problem.day_cost(order, day, weather=False)
        timed = [i for i in problem.timed_stops(order, day) if i not in problem.protected]
        droppable = [i for i in order if i not in problem.protected]
        if shorten and cost.length > problem.budgets[day]:
            droppable = [
                i
                for i in droppable
                if problem.day_cost([j for j in order if j != i], day, weather=False).length
                < cost.length
            ]
        if cost.late and timed:
            candidates, dropped = timed, closed
        elif cost.length > problem.budgets[day] and len(order) > 1 and droppable:
            candidates, dropped = droppable, over
        else:
            break
        worst = max(candidates, key=lambda i: (not problem.stops[i].required, problem.rank[i]))
        dropped.append(worst)
        order = problem.solve_day([i for i in order if i != worst], day)
    return order, over, closed


def _make_room(
    problem: _Problem, order: Sequence[int], stop: int, day: int
) -> tuple[list[int], list[int]] | None:
    """Add `stop` to a day, dropping its least important optional stops until it fits."""
    if problem.hopeless(stop, day):
        return None
    new_order = problem.solve_day([*order, stop], day)
    removed: list[int] = []
    while not problem.fits(cost := problem.day_cost(new_order, day, weather=False), day):
        candidates = problem.timed_stops(new_order, day) if cost.late else new_order
        optional = [i for i in candidates if not problem.stops[i].required]
        if not optional:
            return None
        worst = max(optional, key=lambda i: problem.rank[i])
        removed.append(worst)
        new_order = problem.solve_day([i for i in new_order if i != worst], day)
    return new_order, removed


def _place_required(
    problem: _Problem, day_orders: list[list[int]], dropped: list[int]
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
            placed = _make_room(problem, order, stop, d)
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


def _rebalance(problem: _Problem, day_orders: list[list[int]]) -> list[list[int]]:
    """Move stops between days while that cuts total travel time and every day fits.

    The initial splits keep days equal in stop count; real days are limited by time, so a
    dense neighbourhood can take more stops than a spread-out one.
    """
    days = [list(order) for order in day_orders]
    costs = [problem.day_cost(order, d, weather=False) for d, order in enumerate(days)]
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
                    new_a, new_b = (
                        problem.solve_day(without, a),
                        problem.solve_day([*days[b], stop], b),
                    )
                    cost_a = problem.day_cost(new_a, a, weather=False)
                    cost_b = problem.day_cost(new_b, b, weather=False)
                    if not problem.fits(cost_b, b) or cost_a.late > costs[a].late:
                        continue
                    if cost_a.length > max(problem.budgets[a], costs[a].length):
                        continue
                    old = problem.cost(days[a]) + problem.cost(days[b])
                    if problem.cost(new_a) + problem.cost(new_b) < old - EPS:
                        days[a], days[b] = new_a, new_b
                        costs[a], costs[b] = cost_a, cost_b
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return days


def _reorderings(order: Sequence[int], keep: int = 0) -> Iterator[list[int]]:
    """Orders one move away: a stop moved elsewhere, two stops swapped, a run reversed. The
    first `keep` stops stay where they are."""
    head, tail = list(order[:keep]), list(order[keep:])
    n = len(tail)
    for i in range(n):
        rest = [*tail[:i], *tail[i + 1 :]]
        for j in range(n):
            if j != i:
                yield [*head, *rest[:j], tail[i], *rest[j:]]
    for i in range(n):
        for j in range(i + 1, n):
            swapped = list(tail)
            swapped[i], swapped[j] = swapped[j], swapped[i]
            yield [*head, *swapped]
    for i in range(n):
        for j in range(i + 3, n + 1):  # runs of two are swaps
            yield [*head, *tail[:i], *reversed(tail[i:j]), *tail[j:]]


def _improve_day(
    problem: _Problem, order: Sequence[int], day: int, limit: int, *, weather: bool = True
) -> list[int]:
    """First-improvement local search for travel, lateness and weather, within `limit`
    minutes."""
    best = list(order)
    best_cost = problem.day_cost(best, day, weather=weather).total
    improved = True
    while improved:
        improved = False
        for candidate in _reorderings(best, problem.fixed(best)):
            cost = problem.day_cost(candidate, day, weather=weather)
            if cost.total < best_cost - EPS and cost.length <= limit:
                best, best_cost, improved = candidate, cost.total, True
                break
    return best


def _reorder(
    problem: _Problem,
    order: Sequence[int],
    day: int,
    limit: int | None = None,
    *,
    weather: bool = True,
) -> list[int]:
    """Reorder a day whose outdoor stops meet bad weather or whose visits run late.

    The day keeps to `limit`: the budget (or its current length, if that is longer already).
    Also tried from the reversed order, as a day often just needs turning around, and for
    late visits from the order of closing times. The first stop, if any, stays first.
    """
    current = problem.day_cost(order, day, weather=weather)
    if current.bad <= EPS and not current.late:
        return list(order)
    if limit is None:
        limit = max(problem.budgets[day], current.length)
    keep = problem.fixed(order)
    head, tail = list(order[:keep]), list(order[keep:])
    seeds = [list(order)]
    if problem.day_cost(head + tail[::-1], day, weather=weather).length <= limit:
        seeds.append(head + tail[::-1])
    if current.late:
        # Stable: stops that close at the same time keep their order.
        seeds.append(head + sorted(tail, key=lambda i: problem.opening[day][i][::-1]))
    improved = [_improve_day(problem, seed, day, limit, weather=weather) for seed in seeds]
    return min(improved, key=lambda o: problem.day_cost(o, day, weather=weather).total)


def _assign_dates(problem: _Problem, day_orders: list[list[int]]) -> list[list[int]]:
    """Put each day's stops on the trip date where they meet the least bad weather.

    Every assignment is tried (7! for a week); a date whose budget a day's stops overflow
    (more than on their own date) is not an option for them. Unless one is better, days keep
    their order, so day 1 still holds the most important stop.
    """
    n = len(day_orders)

    def on_date(i: int, d: int) -> float:
        order = day_orders[i]
        limit = max(problem.budgets[d], problem.day_cost(order, i).length)
        costs = [problem.day_cost(o, d) for o in (order, order[::-1])]
        return min((c.total for c in costs if c.length <= limit), default=inf)

    cost = [[on_date(i, d) for d in range(n)] for i in range(n)]

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
        cost = problem.day_cost(new, day)
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
                if without and problem.day_cost(without, a).length <= limits[a]:
                    moved = _best_insertion(problem, other, stop, b, limits[b])
                    if moved is not None:
                        yield a, b, without, moved
                for indoor in (i for i in other if not problem.stops[i].outdoor):
                    into_a = _best_insertion(problem, without, indoor, a, limits[a])
                    rest = [i for i in other if i != indoor]
                    into_b = _best_insertion(problem, rest, stop, b, limits[b])
                    if into_a is not None and into_b is not None:
                        yield a, b, into_a, into_b


def _trade_days(problem: _Problem, day_orders: list[list[int]]) -> list[list[int]]:
    """Make the best trade of outdoor stops between days while one lowers travel time plus
    weather penalty, then reorder the two days it changed."""
    days = [list(order) for order in day_orders]
    for _ in range(MAX_WEATHER_TRADES):
        costs = [problem.day_cost(order, d) for d, order in enumerate(days)]
        limits = [max(problem.budgets[d], cost.length) for d, cost in enumerate(costs)]
        best_gain, best = EPS, None
        for a, b, new_a, new_b in _trades(problem, days, limits):
            after = problem.day_cost(new_a, a).total + problem.day_cost(new_b, b).total
            gain = costs[a].total + costs[b].total - after
            if gain > best_gain:
                best_gain, best = gain, (a, b, new_a, new_b)
        if best is None:
            break
        a, b, new_a, new_b = best
        days[a] = _reorder(problem, new_a, a, limits[a])
        days[b] = _reorder(problem, new_b, b, limits[b])
    return days


def _weather_schedule(problem: _Problem, day_orders: list[list[int]]) -> list[list[int]]:
    """Days on the dates that suit them, each day reordered, then trades between days."""
    dated = _assign_dates(problem, day_orders)
    dated = [_reorder(problem, order, d) for d, order in enumerate(dated)]
    return _trade_days(problem, dated)


@dataclass(frozen=True)
class _Solution:
    strategy: str
    day_orders: list[list[int]]  # by trip day; a day with no stops is empty
    dropped: list[int]
    warnings: list[str]


def _drop_warnings(
    problem: _Problem, days: int, dropped: Sequence[int], closed: Collection[int]
) -> list[str]:
    warnings = []
    shut = sum(i in closed for i in dropped)
    if over := len(dropped) - shut:
        budgets = set(problem.budgets[:days])
        fit = f"{duration_label(budgets.pop())} days" if len(budgets) == 1 else "the days' hours"
        warnings.append(f"dropped {over} stop(s) to fit {fit}")
    if shut:
        warnings.append(f"dropped {shut} stop(s) that are closed or dark in the day's hours")
    if missed := sum(problem.stops[i].required for i in dropped):
        warnings.append(f"{missed} must-visit stop(s) do not fit any day")
    return warnings


def _solve(problem: _Problem, days: int, enforce_budget: bool) -> _Solution:
    candidates = {
        name: [problem.solve_day(group, d) for d, group in enumerate(groups)]
        for name, groups in _split_strategies(problem, days).items()
    }
    strategy, day_orders = min(
        candidates.items(), key=lambda item: sum(problem.cost(o) for o in item[1])
    )
    day_orders = _rebalance(problem, day_orders)

    dropped: list[int] = []
    closed: set[int] = set()

    def fit(d: int, order: list[int]) -> list[int]:
        order, over, shut = _fit_budget(problem, order, d)
        dropped.extend(over + shut)
        closed.update(shut)
        return order

    if enforce_budget:
        day_orders = [fit(d, order) for d, order in enumerate(day_orders)]
        dropped[:] = _place_required(problem, day_orders, dropped)

    if problem.uniform:
        # Day 1 holds the most important stop, and so on, unless the weather says otherwise.
        day_orders = [order for order in day_orders if order]
        day_orders.sort(key=lambda order: min(problem.rank[i] for i in order))
    if problem.conditions is not None:
        day_orders = _weather_schedule(problem, day_orders)
    if problem.timed:
        # On the dates they ended up on, days keep to their hours (daylight differs a bit).
        day_orders = [_reorder(problem, order, d) for d, order in enumerate(day_orders)]
        if enforce_budget:
            day_orders = [fit(d, order) for d, order in enumerate(day_orders)]
    warnings = _drop_warnings(problem, days, dropped, closed) if enforce_budget else []
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
    windows: Sequence[DayWindow] | None = None,
) -> RoutePlan:
    """`windows`, one per trip day in date order, are the days' hours (by default 09:30 to
    21:30); `conditions`, likewise, make the plan weather-aware. Plan day N is trip day N.

    Raises NothingFitsError when no stop can be visited in the days' hours.
    """
    if not stops:
        raise ValueError("no stops to plan")
    transit_threshold_m(modes)  # fail on no modes before any routing request
    if conditions is not None and len(conditions) < days:
        raise ValueError(f"weather conditions for {len(conditions)} of {days} days")
    if windows is not None and len(windows) < days:
        raise ValueError(f"hours for {len(windows)} of {days} days")
    warnings: list[str] = []
    if days > len(stops):
        warnings.append(f"only {len(stops)} stops for {days} days; using {len(stops)} days")
        days = len(stops)
    hours = list(windows[:days]) if windows is not None else [DayWindow()] * days

    points = [LatLon(s.lat, s.lon) for s in stops] + (
        [LatLon(start.lat, start.lon)] if start else []
    )
    distances = await provider.matrix(points)

    home = len(stops) if start else None
    routes: dict[tuple[int, int], TransitRoute | None] = {}
    for attempt in range(TRANSIT_ROUNDS + 1):
        problem = _Problem(
            distances.matrix,
            stops,
            start=home,
            end=home if start and start.round_trip else None,
            modes=modes,
            routes=routes,
            windows=hours,
            budgets=[w.budget(pace) for w in hours],
            conditions=conditions,
        )
        solution = _solve(problem, days, enforce_budget)
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
    for index, order in enumerate(day_orders):
        if not order:
            continue
        visits, cost = problem.schedule(order, index)
        legs = problem.day_legs(order)
        path_points = [points[i] for i in problem.path(order)]
        if problem.round_trip:
            path_points = path_points[:-1]
        plans.append(
            DayPlan(
                day=index + 1,
                visits=visits,
                return_leg=legs[-1] if problem.round_trip else None,
                distance_m=sum(leg.distance_m for leg in legs),
                walking_m=sum(leg.walking_m for leg in legs),
                transit_legs=sum(leg.mode == "transit" for leg in legs),
                total_min=cost.length,
                self_intersections=count_self_intersections(path_points, closed=problem.round_trip),
                window=hours[index],
            )
        )
    if not plans:
        raise NothingFitsError("none of the stops can be visited in the days' hours")
    return RoutePlan(
        days=plans,
        strategy=strategy,
        distance_source=distances.source,
        dropped=sorted((stops[i] for i in dropped), key=lambda s: s.priority),
        warnings=warnings,
    )


@dataclass(frozen=True)
class DayReplan:
    day: DayPlan
    distance_source: DistanceSource
    # Stops of the rest left out because the day would run past its end (`full_end_min`:
    # when it would end with every stop), or reach them closed or dark.
    over: list[Stop]
    closed: list[Stop]
    full_end_min: int
    # When the day ends (back at the hotel on round trips): past the end of its hours plus
    # REPLAN_GRACE_MIN only when the stops that are never dropped take that long.
    end_min: int
    # Stops that are never dropped but still run past closing time or sunset.
    late: list[Stop]


async def replan_day(
    done: Sequence[Stop],
    stops: Sequence[Stop],
    *,
    window: DayWindow,
    provider: DistanceProvider,
    start: StartPoint | None = None,
    origin: Origin | None = None,
    first: int | None = None,
    protected: Collection[int] = (),
    modes: Collection[TravelMode] = ALL_MODES,
    transit: TransitProvider | None = None,
    conditions: DayConditions | None = None,
) -> DayReplan:
    """Plan the rest of a day again. `done`, the visited stops, stay first in their order,
    from `start` (the hotel, if any) as the day's hours begin. The rest, `stops`, begins at
    `origin` if given, else where `done` ends (or where the day starts); `first`, a stop id,
    comes first, and the day ends at `start` on round trips.

    The rest may take until the end of the day's hours plus REPLAN_GRACE_MIN. Stops are
    dropped only beyond that, or when they would be reached closed or dark: least important
    first, and never must-visit stops, `protected` ones (ids) or `first`.

    Raises NothingFitsError when the rest would begin after that, or no stop is left.
    """
    if not done and not stops:
        raise ValueError("no stops to plan")
    if first is not None and first not in {s.id for s in stops}:
        raise ValueError("the first stop must be one of the stops to plan")
    transit_threshold_m(modes)  # fail on no modes before any routing request
    everything = [*done, *stops]
    points = [LatLon(s.lat, s.lon) for s in everything]
    home = here = None
    if start:
        home = len(points)
        points.append(LatLon(start.lat, start.lon))
    if origin:
        here = len(points)
        points.append(LatLon(origin.lat, origin.lon))
    distances = await provider.matrix(points)

    k = len(done)
    rest = list(range(k, len(everything)))
    index = {s.id: i for i, s in enumerate(everything)}
    head = index[first] if first is not None else None
    keep = {index[i] for i in protected if i in index} | {i for i in rest if everything[i].required}
    keep |= {head} if head is not None else set()
    end = home if start and start.round_trip else None

    routes: dict[tuple[int, int], TransitRoute | None] = {}
    for attempt in range(TRANSIT_ROUNDS + 1):
        before = _Problem(
            distances.matrix,
            everything,
            start=home,
            end=None,
            modes=modes,
            routes=routes,
            windows=[window],
            budgets=[window.length_min],
        )
        visited, visited_cost = before.schedule(range(k), 0)
        begin = here if here is not None else (k - 1 if done else home)
        begin_min = visited[-1].leave_min if visited else window.start_min
        if origin and origin.minute is not None:
            begin_min = origin.minute
        until = min(window.end_min + REPLAN_GRACE_MIN, begin_min + MINUTES_PER_DAY)
        if begin_min >= until:
            raise NothingFitsError("the day's hours are over before the rest of it begins")
        hours = DayWindow(begin_min, until, window.sunrise_min, window.sunset_min)
        after = _Problem(
            distances.matrix,
            everything,
            start=begin,
            end=end,
            modes=modes,
            routes=routes,
            windows=[hours],
            budgets=[hours.length_min],  # the end of the hours, not the pace
            conditions=[conditions] if conditions else None,
            first=head,
            protected=keep,
        )
        order = after.solve_day(rest, 0)
        full_end_min = begin_min + after.day_cost(order, 0, weather=False).length
        order, over, closed = _fit_budget(after, order, 0, shorten=True)
        if conditions is not None:
            order = _reorder(after, order, 0)
        if after.timed:
            order = _reorder(after, order, 0)
            order, more_over, more_closed = _fit_budget(after, order, 0, shorten=True)
            over, closed = over + more_over, closed + more_closed
        if transit is None or attempt == TRANSIT_ROUNDS:
            break
        pairs = before.unknown_rides([list(range(k))]) + after.unknown_rides([order])
        unknown = list(dict.fromkeys(pairs))
        if not unknown:
            break
        found = await transit.routes([(points[a], points[b]) for a, b in unknown])
        routes.update(zip(unknown, found, strict=True))

    later, cost = after.schedule(order, 0)
    if origin and later:
        later[0] = replace(later[0], origin=replace(origin, minute=begin_min))
    visits = visited + later
    if not visits:
        raise NothingFitsError("none of the stops can be visited in the rest of the day")
    last = order[-1] if order else k - 1
    return_leg = after.legs[last][end] if end is not None else None
    if order:
        rest_min = cost.length  # the way back included
        end_min = begin_min + cost.length
    else:
        rest_min = round(return_leg.minutes) if return_leg else 0
        end_min = visited[-1].leave_min + rest_min
    legs = [v.leg for v in visits if v.leg is not None] + ([return_leg] if return_leg else [])
    path_points = [points[i] for i in before.path(range(k))]
    if here is not None and later:
        path_points.append(points[here])
    path_points += [points[i] for i in order] + ([points[end]] if end is not None else [])
    closes = [after.opening[0][i][1] for i in order]
    return DayReplan(
        day=DayPlan(
            day=1,
            visits=visits,
            return_leg=return_leg,
            distance_m=sum(leg.distance_m for leg in legs),
            walking_m=sum(leg.walking_m for leg in legs),
            transit_legs=sum(leg.mode == "transit" for leg in legs),
            total_min=visited_cost.length + rest_min,
            self_intersections=count_self_intersections(path_points),
            window=window,
        ),
        distance_source=distances.source,
        over=sorted((everything[i] for i in over), key=lambda s: s.priority),
        closed=sorted((everything[i] for i in closed), key=lambda s: s.priority),
        full_end_min=full_end_min,
        end_min=end_min,
        late=[v.stop for v, close in zip(later, closes, strict=True) if v.leave_min > close],
    )
