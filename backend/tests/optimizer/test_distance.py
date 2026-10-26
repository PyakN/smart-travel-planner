import asyncio
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.optimizer.distance import (
    DETOUR_FACTOR,
    HaversineProvider,
    OsrmProvider,
    haversine_matrix,
    symmetrize,
)
from app.optimizer.factory import create_distance_provider
from app.optimizer.geometry import LatLon

COMERCIO = LatLon(38.7075, -9.1364)
CASTELO = LatLon(38.7139, -9.1335)
LUZIA = LatLon(38.7116, -9.1301)
POINTS = [COMERCIO, CASTELO, LUZIA]


def osrm(handler: Any) -> OsrmProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OsrmProvider("https://osrm.test/routed-foot/", client=client)


def test_haversine_matrix_applies_detour_factor() -> None:
    m = haversine_matrix(POINTS)
    assert m[0][0] == 0
    assert m[0][1] == m[1][0]
    assert m[0][1] == pytest.approx(DETOUR_FACTOR * 755, rel=0.02)
    assert asyncio.run(HaversineProvider().matrix(POINTS)).source == "haversine"


def test_symmetrize() -> None:
    assert symmetrize([[0, 10], [20, 0]]) == [[0, 15], [15, 0]]


def test_osrm_request_and_symmetrized_result() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {"code": "Ok", "distances": [[0, 1000, 900], [1050, 0, 480], [980, 470, 0]]}
        return httpx.Response(200, json=body)

    result = asyncio.run(osrm(handler).matrix(POINTS))
    assert result.source == "osrm"
    assert result.matrix[0][1] == result.matrix[1][0] == 1025
    url = seen[0].url
    coords = "-9.136400,38.707500;-9.133500,38.713900;-9.130100,38.711600"
    assert url.path == f"/routed-foot/table/v1/driving/{coords}"
    assert url.params["annotations"] == "distance"


def test_osrm_null_cells_are_estimated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "Ok", "distances": [[0, None], [None, 0]]})

    result = asyncio.run(osrm(handler).matrix(POINTS[:2]))
    assert result.source == "osrm"
    assert result.matrix[0][1] == pytest.approx(haversine_matrix(POINTS[:2])[0][1])


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="busy"),
        httpx.Response(200, json={"code": "NoTable"}),
        httpx.Response(200, json={"code": "Ok", "distances": [[0]]}),  # wrong shape
        httpx.Response(200, text="<html>"),
    ],
)
def test_osrm_failures_fall_back_to_haversine(response: httpx.Response) -> None:
    result = asyncio.run(osrm(lambda request: response).matrix(POINTS))
    assert result.source == "haversine"
    assert result.matrix == haversine_matrix(POINTS)


def test_osrm_network_error_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert asyncio.run(osrm(handler).matrix(POINTS)).source == "haversine"


@pytest.mark.parametrize(
    ("routing_provider", "expected"), [("osrm", OsrmProvider), ("haversine", HaversineProvider)]
)
def test_factory(routing_provider: str, expected: type) -> None:
    settings = Settings(_env_file=None, database_url="x", routing_provider=routing_provider)
    assert isinstance(create_distance_provider(settings), expected)


def test_osrm_skips_request_for_too_many_points() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called")

    provider = osrm(handler)
    provider.max_points = 2
    assert asyncio.run(provider.matrix(POINTS)).source == "haversine"
