"""Split a trip's stops into days of (nearly) equal size."""

from collections.abc import Callable, Sequence
from math import ceil, inf

from app.optimizer.geometry import LatLon, project

MAX_ITERATIONS = 50


def day_sizes(n: int, days: int) -> tuple[int, int]:
    """Smallest and largest allowed day size for `n` stops over `days` days."""
    return n // days, ceil(n / days)


def _sq(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def balanced_kmeans(points: Sequence[LatLon], days: int) -> list[list[int]]:
    """Geographic clusters with at most ceil(n / days) stops each.

    Deterministic: farthest-point initialisation and capacity-constrained greedy assignment
    (closest point-centre pairs first) instead of random restarts.
    """
    n = len(points)
    if days <= 0:
        raise ValueError("days must be positive")
    if n <= days:
        return [[i] for i in range(n)] + [[] for _ in range(days - n)]

    xy = project(points)
    centroid = (sum(x for x, _ in xy) / n, sum(y for _, y in xy) / n)
    centers = [max(xy, key=lambda p: _sq(p, centroid))]
    while len(centers) < days:
        centers.append(max(xy, key=lambda p: min(_sq(p, c) for c in centers)))

    capacity = day_sizes(n, days)[1]
    assignment: list[int] = []
    for _ in range(MAX_ITERATIONS):
        pairs = sorted((_sq(xy[i], centers[c]), i, c) for i in range(n) for c in range(days))
        new_assignment, sizes = [-1] * n, [0] * days
        for _, i, c in pairs:
            if new_assignment[i] == -1 and sizes[c] < capacity:
                new_assignment[i] = c
                sizes[c] += 1
        if new_assignment == assignment:
            break
        assignment = new_assignment
        for c in range(days):
            members = [xy[i] for i in range(n) if assignment[i] == c]
            if members:
                centers[c] = (
                    sum(x for x, _ in members) / len(members),
                    sum(y for _, y in members) / len(members),
                )
    return [[i for i in range(n) if assignment[i] == c] for c in range(days)]


def split_sequence[T](
    sequence: Sequence[T],
    days: int,
    day_cost: Callable[[Sequence[T]], float],
    min_size: int | None = None,
    max_size: int | None = None,
) -> list[list[T]] | None:
    """Cut an ordered sequence into `days` contiguous chunks with minimum total cost.

    Chunk sizes default to balanced (n // days .. ceil(n / days)). `day_cost` may return
    `inf` for an infeasible chunk; returns None if no feasible split exists.
    """
    n = len(sequence)
    if n <= days:
        return [[item] for item in sequence] + [[] for _ in range(days - n)]
    low, high = day_sizes(n, days)
    low = low if min_size is None else max(1, min_size)
    high = high if max_size is None else min(n, max_size)

    chunk_costs: dict[tuple[int, int], float] = {}

    def chunk_cost(j: int, i: int) -> float:
        if (j, i) not in chunk_costs:
            chunk_costs[(j, i)] = day_cost(sequence[j:i])
        return chunk_costs[(j, i)]

    # best[d][i]: minimum cost of covering the first i items with d days.
    best = [[inf] * (n + 1) for _ in range(days + 1)]
    cut: list[list[int]] = [[0] * (n + 1) for _ in range(days + 1)]
    best[0][0] = 0.0
    for d in range(1, days + 1):
        for i in range(1, n + 1):
            for size in range(low, high + 1):
                j = i - size
                if j < 0 or best[d - 1][j] == inf:
                    continue
                cost = best[d - 1][j] + chunk_cost(j, i)
                if cost < best[d][i]:
                    best[d][i], cut[d][i] = cost, j
    if best[days][n] == inf:
        return None

    chunks: list[list[T]] = []
    i = n
    for d in range(days, 0, -1):
        j = cut[d][i]
        chunks.append(list(sequence[j:i]))
        i = j
    return chunks[::-1]
