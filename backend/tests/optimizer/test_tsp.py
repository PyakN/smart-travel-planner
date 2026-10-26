import random
from itertools import permutations
from math import dist

import pytest

from app.optimizer.distance import Matrix
from app.optimizer.tsp import order_stops, path_cost, solve_path


def euclidean(points: list[tuple[float, float]]) -> Matrix:
    return [[dist(a, b) for b in points] for a in points]


def random_matrix(rng: random.Random, n: int) -> Matrix:
    return euclidean([(rng.uniform(0, 1000), rng.uniform(0, 1000)) for _ in range(n)])


def brute_force(matrix: Matrix, nodes: list[int], start: int | None, round_trip: bool) -> float:
    best = float("inf")
    for perm in permutations(nodes):
        path = ([start] if start is not None else []) + list(perm)
        if round_trip and start is not None:
            path.append(start)
        best = min(best, path_cost(matrix, path))
    return best


def cost_of(matrix: Matrix, order: list[int], start: int | None, round_trip: bool = False) -> float:
    path = ([start] if start is not None else []) + order
    if round_trip and start is not None:
        path.append(start)
    return path_cost(matrix, path)


def test_points_on_a_line_are_visited_in_order() -> None:
    m = euclidean([(0, 0), (30, 0), (10, 0), (20, 0), (40, 0)])
    assert order_stops(m, [1, 2, 3, 4], start=0) == [2, 3, 1, 4]


def test_round_trip_does_not_repeat_start() -> None:
    m = euclidean([(0, 0), (10, 0), (10, 10), (0, 10)])
    order = order_stops(m, [1, 2, 3], start=0, round_trip=True)
    assert sorted(order) == [1, 2, 3]
    assert cost_of(m, order, 0, round_trip=True) == pytest.approx(40)


def test_free_start_picks_an_end_of_the_line() -> None:
    m = euclidean([(20, 0), (0, 0), (40, 0), (10, 0), (30, 0)])
    order = order_stops(m, [0, 1, 2, 3, 4])
    assert order in ([1, 3, 0, 4, 2], [2, 4, 0, 3, 1])


@pytest.mark.parametrize("n_nodes", [0, 1, 2])
def test_tiny_inputs(n_nodes: int) -> None:
    m = euclidean([(0, 0), (5, 5), (9, 1)])
    nodes = list(range(1, n_nodes + 1))
    assert sorted(order_stops(m, nodes, start=0)) == nodes
    assert sorted(order_stops(m, nodes)) == nodes


@pytest.mark.parametrize(
    ("start", "round_trip"), [(0, False), (0, True), (None, False)], ids=["open", "round", "free"]
)
def test_matches_brute_force_on_small_instances(start: int | None, round_trip: bool) -> None:
    rng = random.Random(42)
    gaps = []
    for _ in range(40):
        m = random_matrix(rng, 8)
        nodes = list(range(1, 8)) if start is not None else list(range(8))
        found = cost_of(
            m, order_stops(m, nodes, start=start, round_trip=round_trip), start, round_trip
        )
        optimum = brute_force(m, nodes, start, round_trip)
        assert found >= optimum - 1e-6
        gaps.append(found / optimum - 1)
    assert max(gaps) < 0.05
    assert sum(gaps) / len(gaps) < 0.005


def test_never_worse_than_initial_order() -> None:
    rng = random.Random(7)
    for _ in range(20):
        m = random_matrix(rng, 15)
        initial = list(range(1, 15))
        rng.shuffle(initial)
        order = order_stops(m, initial, start=0, initial=initial)
        assert cost_of(m, order, 0) <= cost_of(m, initial, 0) + 1e-9


def test_initial_must_match_nodes() -> None:
    m = euclidean([(0, 0), (1, 1), (2, 2)])
    with pytest.raises(ValueError):
        solve_path(m, [1, 2], start=0, initial=[1])


def test_scales_to_a_multi_day_trip() -> None:
    m = random_matrix(random.Random(1), 60)
    order = order_stops(m, list(range(60)))
    assert sorted(order) == list(range(60))
