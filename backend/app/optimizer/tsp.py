"""Shortest walking order through a few dozen stops: nearest neighbour + 2-opt + Or-opt.

Nodes are matrix indices and the matrix must be symmetric. The core routine orders the
nodes between a fixed start and an optional fixed end; a free start is a zero-distance
dummy node, and a round trip is "end = start".
"""

from collections.abc import Sequence

from app.optimizer.distance import Matrix

EPS = 1e-9
MAX_SEGMENT = 3  # Or-opt moves chains of up to this many stops


def path_cost(matrix: Matrix, path: Sequence[int], closed: bool = False) -> float:
    cost = sum(matrix[a][b] for a, b in zip(path, path[1:], strict=False))
    if closed and len(path) > 1:
        cost += matrix[path[-1]][path[0]]
    return cost


def _nearest_neighbour(matrix: Matrix, start: int, nodes: Sequence[int]) -> list[int]:
    remaining, order, current = set(nodes), [], start
    while remaining:
        current = min(remaining, key=lambda n: (matrix[current][n], n))
        order.append(current)
        remaining.remove(current)
    return order


def _improve(matrix: Matrix, start: int, seq: list[int], end: int | None) -> list[int]:
    """Local search on [start, *seq, end?]; returns the improved full path."""
    full = [start, *seq] + ([end] if end is not None else [])
    m = len(seq)

    def d(a: int | None, b: int | None) -> float:
        return 0.0 if a is None or b is None else matrix[a][b]

    def at(pos: int) -> int | None:
        return full[pos] if pos < len(full) else None  # past the open end

    improved = True
    while improved:
        improved = False

        # 2-opt: reverse full[i..j].
        for i in range(1, m):
            for j in range(i + 1, m + 1):
                a, b, c, e = full[i - 1], full[i], full[j], at(j + 1)
                if d(a, c) + d(b, e) - d(a, b) - d(c, e) < -EPS:
                    full[i : j + 1] = reversed(full[i : j + 1])
                    improved = True

        # Or-opt: move a chain of 1..MAX_SEGMENT stops elsewhere, possibly reversed.
        for length in range(1, min(MAX_SEGMENT, m) + 1):
            for i in range(1, m - length + 2):
                seg = full[i : i + length]
                prev, nxt = full[i - 1], at(i + length)
                gain = d(prev, seg[0]) + d(seg[-1], nxt) - d(prev, nxt)
                rest = full[:i] + full[i + length :]
                last_slot = len(rest) - (1 if end is not None else 0)
                best_delta, best_move = -EPS, None
                for k in range(last_slot):
                    if k == i - 1:
                        continue
                    left, right = rest[k], rest[k + 1] if k + 1 < len(rest) else None
                    base = d(left, right) + gain
                    forward = d(left, seg[0]) + d(seg[-1], right) - base
                    backward = d(left, seg[-1]) + d(seg[0], right) - base
                    if forward < best_delta:
                        best_delta, best_move = forward, (k, seg)
                    if backward < best_delta:
                        best_delta, best_move = backward, (k, seg[::-1])
                if best_move is not None:
                    k, chain = best_move
                    full = rest[: k + 1] + chain + rest[k + 1 :]
                    improved = True
                    break
            if improved:
                break
    return full


def solve_path(
    matrix: Matrix,
    nodes: Sequence[int],
    start: int,
    end: int | None = None,
    initial: Sequence[int] | None = None,
) -> list[int]:
    """Order `nodes` between `start` and `end`; returns the full path including both.

    With `initial`, that order is also used as a starting point, so the result is never
    longer than it.
    """
    nodes = [n for n in nodes if n != start and n != end]
    seeds = [_nearest_neighbour(matrix, start, nodes)]
    if initial is not None:
        seed = [n for n in initial if n != start and n != end]
        if sorted(seed) != sorted(nodes):
            raise ValueError("initial order must contain exactly the nodes to order")
        seeds.append(seed)
    paths = [_improve(matrix, start, seed, end) for seed in seeds]
    return min(paths, key=lambda path: path_cost(matrix, path))


def with_free_start(matrix: Matrix) -> tuple[Matrix, int]:
    """Append a dummy node at distance 0 from everything; a path from it has a free start."""
    n = len(matrix)
    extended = [[*row, 0.0] for row in matrix] + [[0.0] * (n + 1)]
    return extended, n


def order_stops(
    matrix: Matrix,
    nodes: Sequence[int],
    *,
    start: int | None = None,
    round_trip: bool = False,
    initial: Sequence[int] | None = None,
) -> list[int]:
    """Visiting order of `nodes` (the start node itself is not included)."""
    if start is None:
        extended, dummy = with_free_start(matrix)
        return solve_path(extended, nodes, dummy, initial=initial)[1:]
    path = solve_path(matrix, nodes, start, end=start if round_trip else None, initial=initial)
    return path[1:-1] if round_trip else path[1:]
