"""Walking distance matrices: OSRM (real street network) with a haversine fallback."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.geo import haversine_m
from app.optimizer.geometry import LatLon

logger = logging.getLogger(__name__)

Matrix = list[list[float]]
DistanceSource = Literal["osrm", "haversine"]

# Streets are not straight lines. OSRM foot routes in central Lisbon are ~1.3-1.4x the
# straight-line distance, so the fallback scales haversine to stay comparable.
DETOUR_FACTOR = 1.3


@dataclass(frozen=True)
class DistanceResult:
    matrix: Matrix  # metres, symmetric
    source: DistanceSource


class DistanceProvider(Protocol):
    async def matrix(self, points: Sequence[LatLon]) -> DistanceResult: ...


def haversine_matrix(points: Sequence[LatLon], factor: float = DETOUR_FACTOR) -> Matrix:
    return [[factor * haversine_m(a.lat, a.lon, b.lat, b.lon) for b in points] for a in points]


def symmetrize(matrix: Matrix) -> Matrix:
    """Average both directions; the solvers assume d(a, b) == d(b, a)."""
    n = len(matrix)
    return [[(matrix[i][j] + matrix[j][i]) / 2 for j in range(n)] for i in range(n)]


class HaversineProvider:
    async def matrix(self, points: Sequence[LatLon]) -> DistanceResult:
        return DistanceResult(haversine_matrix(points), "haversine")


class OsrmProvider:
    """OSRM `table` service with a foot profile; falls back to haversine on any failure."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 10.0,
        max_points: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_points = max_points
        self._client = client

    async def matrix(self, points: Sequence[LatLon]) -> DistanceResult:
        if len(points) < 2:
            return DistanceResult(haversine_matrix(points), "haversine")
        if len(points) > self.max_points:
            logger.warning("OSRM: %d points exceed the limit, using haversine", len(points))
            return DistanceResult(haversine_matrix(points), "haversine")
        try:
            return DistanceResult(await self._fetch(points), "osrm")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("OSRM table failed (%r), using haversine", exc)
            return DistanceResult(haversine_matrix(points), "haversine")

    async def _fetch(self, points: Sequence[LatLon]) -> Matrix:
        coords = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in points)
        # The profile segment is ignored by single-profile servers; "driving" is OSRM's default.
        url = f"{self.base_url}/table/v1/driving/{coords}"
        params = {"annotations": "distance"}
        if self._client is not None:
            response = await self._client.get(url, params=params, timeout=self.timeout_s)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=self.timeout_s)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != "Ok":
            raise ValueError(f"OSRM returned {body.get('code')}")
        raw: Matrix = body["distances"]
        if len(raw) != len(points) or any(len(row) != len(points) for row in raw):
            raise ValueError("OSRM matrix has the wrong shape")
        # Unroutable pairs come back as null: estimate them instead of failing the plan.
        fallback = haversine_matrix(points)
        filled = [
            [float(d) if d is not None else fallback[i][j] for j, d in enumerate(row)]
            for i, row in enumerate(raw)
        ]
        return symmetrize(filled)
