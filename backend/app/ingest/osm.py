"""Fetch points of interest from OpenStreetMap (Overpass API) and normalize them."""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.geo import haversine_m
from app.ingest.cities import BBox

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "smart-travel-planner/0.1 (pet project; POI import)"

# Ordered: the first matching rule wins, so specific categories go first
# (a museum inside a palace is a museum; a monastery that is still a church is a landmark).
CATEGORY_RULES: list[tuple[str, frozenset[str], str]] = [
    ("tourism", frozenset({"museum"}), "museum"),
    ("tourism", frozenset({"gallery"}), "gallery"),
    ("amenity", frozenset({"theatre", "arts_centre"}), "culture"),
    ("tourism", frozenset({"viewpoint"}), "viewpoint"),
    ("amenity", frozenset({"marketplace"}), "market"),
    (
        "historic",
        frozenset(
            {
                "castle",
                "palace",
                "fort",
                "tower",
                "city_gate",
                "monastery",
                "aqueduct",
                "ruins",
                "archaeological_site",
                "building",
            }
        ),
        "landmark",
    ),
    ("amenity", frozenset({"place_of_worship"}), "religious"),
    ("historic", frozenset({"church"}), "religious"),
    ("historic", frozenset({"monument", "memorial"}), "monument"),
    ("tourism", frozenset({"artwork"}), "monument"),
    ("leisure", frozenset({"park", "garden"}), "park"),
    ("tourism", frozenset({"attraction", "zoo", "aquarium"}), "attraction"),
]

# Small memorials that are not worth a walk.
SKIP_MEMORIAL_TYPES = frozenset({"plaque", "blue_plaque", "stolperstein"})
SKIP_ACCESS = frozenset({"private", "no"})


@dataclass(frozen=True)
class PlaceRecord:
    osm_type: str
    osm_id: int
    name: str
    category: str
    lat: float
    lon: float
    tags: dict[str, str]

    @property
    def wikidata(self) -> str | None:
        return self.tags.get("wikidata")

    @property
    def opening_hours(self) -> str | None:
        return self.tags.get("opening_hours")

    @property
    def website(self) -> str | None:
        return self.tags.get("website") or self.tags.get("contact:website")


def build_query(bbox: BBox, timeout_s: int = 180) -> str:
    values_by_key: dict[str, set[str]] = defaultdict(set)
    for key, values, _ in CATEGORY_RULES:
        values_by_key[key] |= values

    box = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
    selectors = "\n".join(
        f'  nwr["{key}"~"^({"|".join(sorted(values))})$"]["name"]({box});'
        for key, values in sorted(values_by_key.items())
    )
    # "out center" gives ways and relations a single representative point.
    return f"[out:json][timeout:{timeout_s}];\n(\n{selectors}\n);\nout center tags;"


async def fetch_elements(query: str, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Run the query against the first Overpass mirror that answers."""
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            response = await client.post(
                url, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=240
            )
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json()["elements"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last_error = exc
    raise RuntimeError("All Overpass mirrors failed") from last_error


def categorize(tags: dict[str, str]) -> str | None:
    for key, values, category in CATEGORY_RULES:
        if tags.get(key) in values:
            return category
    return None


def _is_worth_visiting(tags: dict[str, str]) -> bool:
    if tags.get("access") in SKIP_ACCESS:
        return False
    return tags.get("memorial") not in SKIP_MEMORIAL_TYPES


def parse_elements(elements: list[dict[str, Any]]) -> list[PlaceRecord]:
    records: list[PlaceRecord] = []
    for element in elements:
        tags: dict[str, str] = element.get("tags", {})
        name = tags.get("name", "").strip()
        if not name or not _is_worth_visiting(tags):
            continue
        category = categorize(tags)
        if category is None:
            continue
        point = element if element["type"] == "node" else element.get("center")
        if not point or "lat" not in point or "lon" not in point:
            continue
        records.append(
            PlaceRecord(
                osm_type=element["type"],
                osm_id=element["id"],
                name=name,
                category=category,
                lat=point["lat"],
                lon=point["lon"],
                tags=tags,
            )
        )
    return records


def normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.split())


def _quality(record: PlaceRecord) -> tuple[bool, int]:
    return (record.wikidata is not None, len(record.tags))


def deduplicate(records: list[PlaceRecord], radius_m: float = 75.0) -> list[PlaceRecord]:
    """Merge records with the same name that lie within ``radius_m`` of each other.

    OSM often maps one place twice (e.g. an entrance node and a building outline).
    The record with a Wikidata link, then the most tags, is kept.
    """
    by_name: dict[str, list[PlaceRecord]] = defaultdict(list)
    for record in records:
        by_name[normalize_name(record.name)].append(record)

    kept: list[PlaceRecord] = []
    for group in by_name.values():
        survivors: list[PlaceRecord] = []
        for record in sorted(group, key=_quality, reverse=True):
            if all(
                haversine_m(record.lat, record.lon, other.lat, other.lon) > radius_m
                for other in survivors
            ):
                survivors.append(record)
        kept.extend(survivors)
    return kept
