from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, radians

from app.geo import EARTH_RADIUS_M


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


def project(points: Sequence[LatLon]) -> list[tuple[float, float]]:
    """Equirectangular projection to metres around the points' mean latitude.

    Accurate to well under 1% at city scale, which is all clustering and
    intersection tests need.
    """
    if not points:
        return []
    lat0 = radians(sum(p.lat for p in points) / len(points))
    k = radians(1) * EARTH_RADIUS_M
    return [(p.lon * k * cos(lat0), p.lat * k) for p in points]


Segment = tuple[tuple[float, float], tuple[float, float]]


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(s: Segment, t: Segment) -> bool:
    """True if the segments properly cross (shared endpoints and collinear overlap don't count)."""
    d1, d2 = _orientation(*t, s[0]), _orientation(*t, s[1])
    d3, d4 = _orientation(*s, t[0]), _orientation(*s, t[1])
    return d1 * d2 < 0 and d3 * d4 < 0


def count_self_intersections(points: Sequence[LatLon], closed: bool = False) -> int:
    """Number of crossing pairs of non-adjacent legs in a polyline: the route's "zigzags"."""
    xy = project(points)
    legs: list[Segment] = list(zip(xy, xy[1:], strict=False))
    if closed and len(xy) > 2:
        legs.append((xy[-1], xy[0]))
    crossings = 0
    for i in range(len(legs)):
        for j in range(i + 2, len(legs)):
            if closed and i == 0 and j == len(legs) - 1:
                continue  # first and last legs share the start point
            if segments_cross(legs[i], legs[j]):
                crossings += 1
    return crossings
