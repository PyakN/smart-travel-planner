import pytest

from app.optimizer.geometry import LatLon, count_self_intersections, project, segments_cross

# A small square in Lisbon, ~100 m per side.
SW = LatLon(38.7, -9.14)
SE = LatLon(38.7, -9.1388)
NE = LatLon(38.7009, -9.1388)
NW = LatLon(38.7009, -9.14)


def test_projection_preserves_distances_at_city_scale() -> None:
    (x0, y0), (x1, y1) = project([SW, SE])
    assert abs(x1 - x0) == pytest.approx(104, rel=0.02)
    assert y1 == pytest.approx(y0)


def test_segments_cross() -> None:
    assert segments_cross(((0, 0), (2, 2)), ((0, 2), (2, 0)))
    assert not segments_cross(((0, 0), (1, 1)), ((2, 2), (3, 0)))
    assert not segments_cross(((0, 0), (2, 0)), ((2, 0), (3, 1)))  # shared endpoint


def test_square_walked_in_order_has_no_crossings() -> None:
    assert count_self_intersections([SW, SE, NE, NW]) == 0
    assert count_self_intersections([SW, SE, NE, NW], closed=True) == 0


def test_bow_tie_has_one_crossing() -> None:
    assert count_self_intersections([SW, NE, SE, NW]) == 1
    assert count_self_intersections([SW, NE, NW, SE], closed=True) == 1


def test_degenerate_routes() -> None:
    assert count_self_intersections([]) == 0
    assert count_self_intersections([SW, NE]) == 0
