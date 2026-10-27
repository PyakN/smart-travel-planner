import asyncio
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.optimizer.factory import create_transit_provider
from app.optimizer.geometry import LatLon
from app.optimizer.transit import HereTransitProvider, departure_time, parse_routes

# Real HERE answers for Lisbon (departure 12:00 on a weekday).
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "here"
FIGUEIRA = LatLon(38.7139, -9.1378)
BELEM = LatLon(38.6967, -9.2030)
API_KEY = "test-key-not-real"


def fixture(name: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return body


def here(handler: Any, **kwargs: Any) -> HereTransitProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HereTransitProvider(
        API_KEY, url="https://transit.test/v8/routes", client=client, **kwargs
    )


def test_parses_metro_then_train() -> None:
    # Praca da Figueira -> Belem: metro Green line to Cais do Sodre, then the Cascais line.
    route = parse_routes(fixture("figueira_belem"))
    assert route is not None
    assert [s.mode for s in route.sections] == ["walk", "transit", "walk", "transit", "walk"]
    assert route.minutes == 24  # 12:13 -> 12:37, the change at Cais do Sodre included
    metro, train = route.rides
    assert (metro.vehicle, metro.line, metro.color) == ("metro", "Verde", "#009933")
    assert (metro.board, metro.alight, metro.stops) == ("Rossio", "Cais do Sodré", 2)
    assert metro.headsign == "Cais Do Sodré"
    assert (train.vehicle, train.line, train.stops, train.minutes) == (
        "train",
        "Linha de Cascais",
        3,
        7,
    )
    assert "Metropolitano de Lisboa" in metro.attributions[0].text
    assert train.attributions[0].url == "http://www.cp.pt"
    assert route.walking_m == 115 + 120 + 572
    assert route.distance_m == 115 + 1171 + 120 + 4775 + 572
    # Decoded paths join up: each section starts close to where the previous one ended.
    for before, after in zip(route.sections, route.sections[1:], strict=False):
        assert abs(before.path[-1].lat - after.path[0].lat) < 0.001
        assert abs(before.path[-1].lon - after.path[0].lon) < 0.001
    assert len(metro.attributions) == 1
    assert route.sections[1].path[0] != route.sections[1].path[-1]


def test_fastest_itinerary_wins() -> None:
    # Baixa -> castle: HERE offers bus 10B (17 min) and a 20-minute walk.
    route = parse_routes(fixture("baixa_castelo"))
    assert route is not None
    assert [r.line for r in route.rides] == ["10B"]
    assert route.minutes == 17


def test_lisbon_trams_are_trams() -> None:
    # HERE calls the 28E a bus.
    route = parse_routes(fixture("martim_estrela"))
    assert route is not None
    assert [(r.vehicle, r.line) for r in route.rides] == [("tram", "28E")]


def test_walk_only_answer_has_no_rides() -> None:
    route = parse_routes(fixture("restauradores_spedro"))  # "too close" notice
    assert route is not None
    assert route.rides == []
    assert route.walking_m == route.distance_m == 624


@pytest.mark.parametrize("body", [{"routes": []}, {"notices": [{"code": "noTransitRouteFound"}]}])
def test_no_itinerary(body: dict[str, Any]) -> None:
    assert parse_routes(body) is None


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 27), "2026-10-28T12:00:00"),  # Tuesday -> Wednesday
        (date(2026, 10, 30), "2026-11-02T12:00:00"),  # Friday -> Monday
        (date(2026, 10, 31), "2026-11-02T12:00:00"),  # Saturday -> Monday
    ],
)
def test_departs_midday_on_the_next_weekday(today: date, expected: str) -> None:
    assert departure_time(today) == expected


def test_request_and_cache() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("figueira_belem"))

    provider = here(handler)
    there, back = (FIGUEIRA, BELEM), (BELEM, FIGUEIRA)
    first = asyncio.run(provider.routes([there, there, back]))
    assert len(seen) == 2  # one request per direction
    assert first[0] is first[1] is not None
    params = seen[0].url.params
    assert (params["origin"], params["destination"]) == (
        "38.713900,-9.137800",
        "38.696700,-9.203000",
    )
    assert params["apiKey"] == API_KEY
    assert set(params["return"].split(",")) == {"polyline", "travelSummary", "intermediate"}
    assert params["departureTime"].endswith("T12:00:00")

    assert asyncio.run(provider.routes([back, there])) == [first[2], first[0]]
    assert len(seen) == 2  # served from the cache


def test_no_itinerary_is_cached() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"routes": []})

    provider = here(handler)
    for _ in range(2):
        assert asyncio.run(provider.routes([(FIGUEIRA, BELEM)])) == [None]
    assert len(seen) == 1


def test_failures_are_retried_by_the_next_plan() -> None:
    responses = [httpx.Response(503), httpx.Response(200, json=fixture("figueira_belem"))]
    provider = here(lambda request: responses.pop(0))
    assert asyncio.run(provider.routes([(FIGUEIRA, BELEM)])) == [None]
    [route] = asyncio.run(provider.routes([(FIGUEIRA, BELEM)]))
    assert route is not None


def test_lru_cache_size() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("figueira_belem"))

    provider = here(handler, cache_size=1)
    for pair in [(FIGUEIRA, BELEM), (BELEM, FIGUEIRA), (FIGUEIRA, BELEM)]:
        asyncio.run(provider.routes([pair]))
    assert len(seen) == 3


def test_rejected_key_turns_the_provider_off() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, json={"error": "Unauthorized"})

    provider = here(handler)
    assert asyncio.run(provider.routes([(FIGUEIRA, BELEM)])) == [None]
    assert not provider.enabled
    assert asyncio.run(provider.routes([(BELEM, FIGUEIRA)])) == [None]
    assert len(seen) == 1


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.Response(500, text="oops"),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"routes": [{"sections": [{"type": "transit"}]}]}),
        httpx.ConnectError("connection refused"),
    ],
)
def test_failures_never_log_the_key(
    outcome: httpx.Response | Exception, caplog: pytest.LogCaptureFixture
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(here(handler).routes([(FIGUEIRA, BELEM)])) == [None]
    assert "HERE transit failed" in caplog.text
    assert API_KEY not in caplog.text


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, type(None)),
        ({"here_api_key": ""}, type(None)),
        ({"here_api_key": "k", "transit_provider": "estimate"}, type(None)),
        ({"here_api_key": "k"}, HereTransitProvider),
    ],
)
def test_factory(overrides: dict[str, Any], expected: type) -> None:
    # Explicit provider: the integration tests set TRANSIT_PROVIDER for the whole session.
    settings = Settings(
        _env_file=None, database_url="x", **{"transit_provider": "here", **overrides}
    )
    assert isinstance(create_transit_provider(settings), expected)
