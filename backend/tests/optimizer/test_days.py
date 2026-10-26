from collections.abc import Sequence

import pytest

from app.optimizer.days import balanced_kmeans, day_sizes, split_sequence
from app.optimizer.geometry import LatLon

# Three neighbourhoods ~2-4 km apart, four stops each.
ALFAMA = [LatLon(38.711 + d, -9.130 + d) for d in (0, 0.001, 0.002, 0.0015)]
BELEM = [LatLon(38.697 + d, -9.206 + d) for d in (0, 0.001, 0.002, 0.0015)]
AVENIDAS = [LatLon(38.737 + d, -9.150 + d) for d in (0, 0.001, 0.002, 0.0015)]


def as_sets(groups: list[list[int]]) -> set[frozenset[int]]:
    return {frozenset(g) for g in groups}


def test_day_sizes() -> None:
    assert day_sizes(12, 3) == (4, 4)
    assert day_sizes(10, 3) == (3, 4)


def test_kmeans_recovers_neighbourhoods() -> None:
    groups = balanced_kmeans(ALFAMA + BELEM + AVENIDAS, days=3)
    assert as_sets(groups) == {
        frozenset(range(0, 4)),
        frozenset(range(4, 8)),
        frozenset(range(8, 12)),
    }


def test_kmeans_respects_capacity() -> None:
    # 8 stops in Alfama, 1 in Belém: two days must still share the work.
    points = [LatLon(38.711 + i * 0.0005, -9.130) for i in range(8)] + BELEM[:1]
    groups = balanced_kmeans(points, days=2)
    assert sorted(len(g) for g in groups) == [4, 5]
    assert sorted(i for g in groups for i in g) == list(range(9))


def test_kmeans_edge_cases() -> None:
    assert balanced_kmeans(ALFAMA, days=1) == [[0, 1, 2, 3]]
    assert balanced_kmeans(ALFAMA[:2], days=3) == [[0], [1], []]
    with pytest.raises(ValueError):
        balanced_kmeans(ALFAMA, days=0)


def spread(chunk: Sequence[float]) -> float:
    return max(chunk) - min(chunk) if chunk else 0.0


def test_split_sequence_cuts_at_the_gaps() -> None:
    positions = [0.0, 1, 2, 100, 101, 102, 200, 201, 202]
    assert split_sequence(positions, 3, spread) == [[0, 1, 2], [100, 101, 102], [200, 201, 202]]


def test_split_sequence_keeps_days_balanced() -> None:
    # The cheapest split would be [0..6] + [100]; balance forces sizes 4 and 4.
    positions = [0.0, 1, 2, 3, 4, 5, 6, 100]
    chunks = split_sequence(positions, 2, spread)
    assert [len(c) for c in chunks] == [4, 4]


def test_split_sequence_fewer_items_than_days() -> None:
    assert split_sequence([1.0, 2.0], 3, spread) == [[1.0], [2.0], []]
