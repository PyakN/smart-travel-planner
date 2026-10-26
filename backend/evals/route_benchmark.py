"""Benchmark: how much walking does the optimizer save compared to LLM-only ordering?

For each eval request (see selection_eval.py) the real LLM selects places, then four
routings are compared on the same OSRM walking-distance matrix:

  A. selection order  - the LLM's ranking cut into days
  B. LLM itinerary    - the LLM arranges days and order itself (given names + coordinates)
  C. optimizer        - our planner on haversine estimates
  D. optimizer        - our planner on OSRM walking distances

OR-Tools (guided local search, 1 s per day) on D's days measures our TSP's optimality gap.
No start point (free start, open end), no time budget: pure distance.

Usage (from backend/): python evals/route_benchmark.py [case-name ...]
"""

import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from pydantic import BaseModel, Field
from selection_eval import CASES

from app.config import get_settings
from app.db.session import create_engine, create_sessionmaker
from app.llm.factory import create_llm_service
from app.llm.service import LLMService
from app.optimizer.days import day_sizes
from app.optimizer.distance import DistanceResult, HaversineProvider, Matrix, OsrmProvider
from app.optimizer.geometry import LatLon, count_self_intersections
from app.optimizer.planner import (
    DAY_BUDGET_MIN,
    WALKING_M_PER_MIN,
    RoutePlan,
    Stop,
    plan_route,
    visit_minutes,
)
from app.optimizer.tsp import path_cost
from app.repositories.candidates import Candidate
from app.schemas.trip import Pace
from app.services.place_selection import select_places

Days = list[list[int]]  # place indices per day, in walking order


class DayOrder(BaseModel):
    place_ids: list[int] = Field(description="Place ids for this day in walking order")


class Itinerary(BaseModel):
    days: list[DayOrder]


ITINERARY_SYSTEM = """You are an expert travel planner. Arrange the given places into the
requested number of days and order each day as an efficient walking route: group nearby
places on the same day and avoid back-and-forth. Use every id exactly once."""


@dataclass
class Row:
    case: str
    stops: int
    days: int
    pace: Pace
    km: dict[str, float]
    crossings: dict[str, int]
    over_budget: dict[str, int]  # days longer than the pace's time budget
    ortools_gap: float
    optimizer_ms: float
    repairs: int


@dataclass
class StaticProvider:
    """Serves a precomputed matrix, so timing measures the optimizer, not the network."""

    result: DistanceResult

    async def matrix(self, points: Sequence[LatLon]) -> DistanceResult:
        return self.result

    async def geometry(self, points: Sequence[LatLon]) -> list[LatLon]:
        return list(points)


def cost(matrix: Matrix, days: Days) -> float:
    return sum(path_cost(matrix, day) for day in days)


def days_over_budget(matrix: Matrix, places: list[Candidate], days: Days, pace: Pace) -> int:
    def minutes(day: list[int]) -> float:
        walk = path_cost(matrix, day) / WALKING_M_PER_MIN
        return walk + sum(visit_minutes(places[i].category) for i in day)

    return sum(minutes(day) > DAY_BUDGET_MIN[pace] for day in days)


def crossings(points: Sequence[LatLon], days: Days) -> int:
    return sum(count_self_intersections([points[i] for i in day]) for day in days)


def chunk_selection_order(n: int, days: int) -> Days:
    low, high = day_sizes(n, days)
    sizes = [high] * (n % days) + [low] * (days - n % days)
    out, pos = [], 0
    for size in sizes:
        out.append(list(range(pos, pos + size)))
        pos += size
    return [d for d in out if d]


async def llm_itinerary(llm: LLMService, places: list[Candidate], days: int) -> tuple[Days, int]:
    lines = "\n".join(f"{p.id} | {p.name} | {p.lat:.5f}, {p.lon:.5f}" for p in places)
    result = await llm.generate(
        system=ITINERARY_SYSTEM,
        prompt=f"Days: {days}\nPlaces (id | name | lat, lon):\n{lines}",
        schema=Itinerary,
    )
    index = {p.id: i for i, p in enumerate(places)}
    seen: set[int] = set()
    out: Days = []
    repairs = 0
    for day in result.days:
        kept = []
        for place_id in day.place_ids:
            if place_id in index and place_id not in seen:
                kept.append(index[place_id])
                seen.add(place_id)
            else:
                repairs += 1
        if kept:
            out.append(kept)
    missing = [i for i, p in enumerate(places) if p.id not in seen]
    if missing:  # forgotten places go to the shortest day, so every routing has the same stops
        repairs += len(missing)
        if not out:
            out.append([])
        min(out, key=len).extend(missing)
    return out, repairs


def plan_days(plan: RoutePlan, places: list[Candidate]) -> Days:
    index = {p.id: i for i, p in enumerate(places)}
    return [[index[v.stop.id] for v in day.visits] for day in plan.days]


def ortools_open_path(matrix: Matrix, nodes: list[int]) -> float:
    if len(nodes) < 3:
        return path_cost(matrix, nodes)
    manager = pywrapcp.RoutingIndexManager(len(nodes) + 1, 1, 0)  # node 0: free depot
    routing = pywrapcp.RoutingModel(manager)

    def distance(i: int, j: int) -> int:
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        return 0 if a == 0 or b == 0 else round(matrix[nodes[a - 1]][nodes[b - 1]])

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance))
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(1)
    return float(routing.SolveWithParameters(params).ObjectiveValue())


async def run_case(name: str, text: str) -> Row:
    settings = get_settings()
    llm = create_llm_service(settings)
    engine = create_engine()
    try:
        async with create_sessionmaker(engine)() as session:
            selection = await select_places(llm, session, text, default_city=settings.default_city)
    finally:
        await engine.dispose()

    places, days = selection.places, min(selection.trip.days, len(selection.places))
    pace = selection.trip.pace
    points = [LatLon(p.lat, p.lon) for p in places]
    stops = [Stop(p.id, p.lat, p.lon, p.category, priority=i) for i, p in enumerate(places)]
    walking = await OsrmProvider(settings.osrm_base_url).matrix(points)
    if walking.source != "osrm":
        raise RuntimeError("OSRM unavailable; the benchmark needs real walking distances")

    routings: dict[str, Days] = {"A": chunk_selection_order(len(places), days)}
    routings["B"], repairs = await llm_itinerary(llm, places, days)
    plan_c = await plan_route(
        stops, days=days, pace=pace, provider=HaversineProvider(), enforce_budget=False
    )
    routings["C"] = plan_days(plan_c, places)
    started = time.perf_counter()
    plan_d = await plan_route(
        stops, days=days, pace=pace, provider=StaticProvider(walking), enforce_budget=False
    )
    optimizer_ms = (time.perf_counter() - started) * 1000
    routings["D"] = plan_days(plan_d, places)

    matrix = walking.matrix
    ortools_total = sum(ortools_open_path(matrix, day) for day in routings["D"])
    return Row(
        case=name,
        stops=len(places),
        days=days,
        pace=pace,
        km={k: cost(matrix, v) / 1000 for k, v in routings.items()},
        crossings={k: crossings(points, v) for k, v in routings.items()},
        over_budget={k: days_over_budget(matrix, places, v, pace) for k, v in routings.items()},
        ortools_gap=cost(matrix, routings["D"]) / ortools_total - 1 if ortools_total else 0.0,
        optimizer_ms=optimizer_ms,
        repairs=repairs,
    )


def saving(row: Row, baseline: str) -> str:
    return f"{100 * (1 - row.km['D'] / row.km[baseline]):.0f}%"


async def main(names: list[str]) -> None:
    cases = [c for c in CASES if not names or c.name in names]
    rows = []
    for case in cases:
        print(f"running {case.name}...", file=sys.stderr)
        rows.append(await run_case(case.name, case.text))

    print(
        "| Case | Stops/days, pace | A: selection order | B: LLM itinerary | C: opt. haversine "
        "| D: opt. OSRM | D vs A | D vs B | Gap to OR-Tools |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        cells = []
        for k in "ABCD":
            cell = f"{r.km[k]:.1f} km, {r.crossings[k]}×"
            if r.over_budget[k]:
                cell += f", **{r.over_budget[k]} day(s) over budget**"
            cells.append(cell)
        print(
            f"| {r.case} | {r.stops}/{r.days}, {r.pace} | {' | '.join(cells)} "
            f"| {saving(r, 'A')} | {saving(r, 'B')} | {100 * r.ortools_gap:+.1f}% |"
        )
    total = {k: sum(r.km[k] for r in rows) for k in "ABCD"}
    print(
        f"\nTotal: A {total['A']:.1f} km, B {total['B']:.1f} km, C {total['C']:.1f} km, "
        f"D {total['D']:.1f} km. D saves {100 * (1 - total['D'] / total['A']):.0f}% vs A and "
        f"{100 * (1 - total['D'] / total['B']):.0f}% vs B."
    )
    print(f"Crossings: {', '.join(f'{k} {sum(r.crossings[k] for r in rows)}' for k in 'ABCD')}")
    over = ", ".join(f"{k} {sum(r.over_budget[k] for r in rows)}" for k in "ABCD")
    print(f"Days over the time budget: {over}")
    print(f"LLM itinerary repairs (bad/missing ids): {sum(r.repairs for r in rows)}")
    print(f"Optimizer time (matrix precomputed): {max(r.optimizer_ms for r in rows):.0f} ms max")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
