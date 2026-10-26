import pytest

from app.geo import EARTH_RADIUS_M, haversine_m


def test_same_point_is_zero() -> None:
    assert haversine_m(38.7075, -9.1364, 38.7075, -9.1364) == 0


def test_one_degree_of_latitude() -> None:
    expected = EARTH_RADIUS_M * 3.141592653589793 / 180  # ~111.2 km
    assert haversine_m(38.0, -9.0, 39.0, -9.0) == pytest.approx(expected, rel=1e-9)


def test_symmetric() -> None:
    a = (38.7075, -9.1364)  # Praça do Comércio
    b = (38.7139, -9.1335)  # Castelo de São Jorge
    assert haversine_m(*a, *b) == pytest.approx(haversine_m(*b, *a))
    assert 700 < haversine_m(*a, *b) < 800
