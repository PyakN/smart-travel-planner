"""Public transport routes between two points: HERE Public Transit API v8.

The optimizer asks for the legs it wants to ride (see app.optimizer.planner). Each answer
is the fastest itinerary at midday on the next weekday: walks to and from the stops, every
ride with its line, and the paths for the map. HERE has no transit matrix, so routes are
fetched per leg and cached per (origin, destination).
"""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, Protocol

import httpx

from app.optimizer import polyline
from app.optimizer.geometry import LatLon

logger = logging.getLogger(__name__)

HERE_TRANSIT_URL = "https://transit.router.hereapi.com/v8/routes"
# Service at midday is typical of the hours a trip day covers (09:30 to the evening).
DEPARTURE_HOUR = 12

Vehicle = Literal["metro", "tram", "bus", "train", "ferry", "funicular", "cable_car", "other"]
_VEHICLES: dict[str, Vehicle] = {
    "subway": "metro",
    "lightRail": "tram",
    "bus": "bus",
    "privateBus": "bus",
    "busRapid": "bus",
    "cityTrain": "train",
    "regionalTrain": "train",
    "interRegionalTrain": "train",
    "intercityTrain": "train",
    "highSpeedTrain": "train",
    "ferry": "ferry",
    "inclined": "funicular",
    "aerial": "cable_car",
}
# HERE lists Carris's trams as buses; these are Lisbon's tram lines.
LISBON_TRAM_LINES = frozenset({"12E", "15E", "18E", "24E", "25E", "28E"})

Pair = tuple[LatLon, LatLon]


class _HideApiKey(logging.Filter):
    """httpx logs request URLs (at INFO level), and HERE takes the key in the query."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                arg.copy_set_param("apiKey", "***")
                if isinstance(arg, httpx.URL) and "apiKey" in arg.params
                else arg
                for arg in record.args
            )
        return True


logging.getLogger("httpx").addFilter(_HideApiKey())


@dataclass(frozen=True)
class Attribution:
    """Data credit the operator requires next to its routes."""

    text: str
    url: str | None


@dataclass(frozen=True)
class Ride:
    vehicle: Vehicle
    line: str  # "28E", "Verde" (metro), "Linha de Cascais"
    headsign: str | None
    color: str | None  # the line's own colour, "#RRGGBB"
    board: str | None  # stop names
    alight: str | None
    stops: int  # stops ridden
    minutes: float
    attributions: tuple[Attribution, ...] = ()


@dataclass(frozen=True)
class Section:
    mode: Literal["walk", "transit"]
    path: tuple[LatLon, ...]
    distance_m: float
    minutes: float
    ride: Ride | None  # None for walks


@dataclass(frozen=True)
class TransitRoute:
    sections: tuple[Section, ...]
    minutes: float  # door to door, waits for connections included

    @property
    def rides(self) -> list[Ride]:
        return [s.ride for s in self.sections if s.ride is not None]

    @property
    def distance_m(self) -> float:
        return sum(s.distance_m for s in self.sections)

    @property
    def walking_m(self) -> float:
        return sum(s.distance_m for s in self.sections if s.mode == "walk")


class TransitProvider(Protocol):
    async def routes(self, pairs: Sequence[Pair]) -> list[TransitRoute | None]:
        """Fastest route for each (origin, destination); None where unknown.

        A route without rides means walking is the fastest way there.
        """
        ...


def departure_time(today: date | None = None) -> str:
    """Midday on the next weekday, local time at the origin (HERE's reading without offset)."""
    day = (today or date.today()) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return f"{day.isoformat()}T{DEPARTURE_HOUR:02d}:00:00"


def _vehicle(transport: dict[str, Any], line: str) -> Vehicle:
    vehicle = _VEHICLES.get(transport.get("mode", ""), "other")
    return "tram" if vehicle == "bus" and line in LISBON_TRAM_LINES else vehicle


def _minutes(section: dict[str, Any]) -> float:
    seconds = section.get("travelSummary", {}).get("duration")
    if seconds is None:
        start = datetime.fromisoformat(section["departure"]["time"])
        seconds = (datetime.fromisoformat(section["arrival"]["time"]) - start).total_seconds()
    return float(seconds) / 60


def _section(raw: dict[str, Any]) -> Section:
    departure, arrival = raw["departure"]["place"], raw["arrival"]["place"]
    if "polyline" in raw:
        path = tuple(polyline.decode(raw["polyline"]))
    else:
        path = tuple(
            LatLon(p["location"]["lat"], p["location"]["lng"]) for p in (departure, arrival)
        )
    distance = float(raw.get("travelSummary", {}).get("length", 0))
    minutes = _minutes(raw)
    if raw["type"] != "transit":
        return Section("walk", path, distance, minutes, None)
    transport = raw["transport"]
    line = transport.get("name") or transport.get("shortName") or transport.get("longName") or ""
    vehicle = _vehicle(transport, line)
    if vehicle == "metro" and transport.get("longName"):
        line = transport["longName"]  # "Verde" reads better than "Vd"
    ride = Ride(
        vehicle=vehicle,
        line=line,
        headsign=transport.get("headsign"),
        color=transport.get("color"),
        board=departure.get("name"),
        alight=arrival.get("name"),
        stops=len(raw.get("intermediateStops", [])) + 1,
        minutes=minutes,
        attributions=tuple(
            Attribution(a["text"], a.get("href")) for a in raw.get("attributions", [])
        ),
    )
    return Section("transit", path, distance, minutes, ride)


def _route(raw: dict[str, Any]) -> TransitRoute:
    sections = raw["sections"]
    start = datetime.fromisoformat(sections[0]["departure"]["time"])
    end = datetime.fromisoformat(sections[-1]["arrival"]["time"])
    return TransitRoute(tuple(map(_section, sections)), (end - start).total_seconds() / 60)


def parse_routes(body: dict[str, Any]) -> TransitRoute | None:
    """The fastest of HERE's itineraries (fewer rides on a tie); None if it found none."""
    routes = [_route(raw) for raw in body.get("routes", [])]
    if not routes:
        return None
    return min(routes, key=lambda r: (r.minutes, len(r.rides)))


class HereTransitProvider:
    """HERE Public Transit API v8, with an LRU cache of answers.

    Failures are not cached: those legs keep the estimate, and the next plan asks again. A
    rejected key turns the provider off until restart instead of failing every leg.
    """

    def __init__(
        self,
        api_key: str,
        *,
        url: str = HERE_TRANSIT_URL,
        timeout_s: float = 8.0,
        max_concurrency: int = 6,
        cache_size: int = 4096,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.url = url
        self.timeout_s = timeout_s
        self.max_concurrency = max_concurrency
        self.cache_size = cache_size
        self._client = client
        self._cache: OrderedDict[Pair, TransitRoute | None] = OrderedDict()
        self.enabled = True

    async def routes(self, pairs: Sequence[Pair]) -> list[TransitRoute | None]:
        known: dict[Pair, TransitRoute | None] = {}
        for pair in pairs:
            if pair in self._cache:
                self._cache.move_to_end(pair)
                known[pair] = self._cache[pair]
        missing = [pair for pair in dict.fromkeys(pairs) if pair not in known]
        if missing and self.enabled:
            limit = asyncio.Semaphore(self.max_concurrency)
            if self._client is not None:
                answers = await asyncio.gather(
                    *(self._ask(self._client, limit, p) for p in missing)
                )
            else:
                async with httpx.AsyncClient() as client:
                    answers = await asyncio.gather(*(self._ask(client, limit, p) for p in missing))
            for pair, (answered, route) in zip(missing, answers, strict=True):
                if answered:
                    known[pair] = route
                    self._remember(pair, route)
        return [known.get(pair) for pair in pairs]

    def _remember(self, pair: Pair, route: TransitRoute | None) -> None:
        self._cache[pair] = route
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    async def _ask(
        self, client: httpx.AsyncClient, limit: asyncio.Semaphore, pair: Pair
    ) -> tuple[bool, TransitRoute | None]:
        """(answered, route): route is None when HERE found no itinerary."""
        origin, destination = pair
        params = {
            "origin": f"{origin.lat:.6f},{origin.lon:.6f}",
            "destination": f"{destination.lat:.6f},{destination.lon:.6f}",
            "departureTime": departure_time(),
            "return": "polyline,travelSummary,intermediate",
            "apiKey": self._api_key,
        }
        try:
            async with limit:
                response = await client.get(self.url, params=params, timeout=self.timeout_s)
            response.raise_for_status()
            return True, parse_routes(response.json())
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                self.enabled = False
                logger.error("HERE rejected the API key (HTTP %d); transit is estimated", status)
            else:
                logger.warning("HERE transit failed (HTTP %d), using an estimate", status)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            # Never the exception text: httpx puts the request URL, API key included, in it.
            logger.warning("HERE transit failed (%s), using an estimate", type(exc).__name__)
        return False, None
