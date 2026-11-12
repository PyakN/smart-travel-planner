"""Fetch points of interest from OpenStreetMap (Overpass API) and normalize them."""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.catalog import VENUE_CATEGORIES, open_building
from app.geo import BBox, haversine_m

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    # VK Maps' public instance: it answered most cities while the other two were down or
    # overloaded (it failed now and then too).
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
USER_AGENT = "smart-travel-planner/0.1 (pet project; POI import)"

# Ordered: the first matching rule wins, so specific categories go first
# (a museum inside a palace is a museum; a monastery that is still a church is a landmark;
# a restaurant in a historic building is a restaurant, a pastry shop that is an attraction
# a café).
CATEGORY_RULES: list[tuple[str, frozenset[str], str]] = [
    ("tourism", frozenset({"museum"}), "museum"),
    ("tourism", frozenset({"gallery"}), "gallery"),
    ("amenity", frozenset({"theatre", "arts_centre"}), "culture"),
    ("tourism", frozenset({"viewpoint"}), "viewpoint"),
    ("amenity", frozenset({"marketplace"}), "market"),
    ("amenity", frozenset({"bar", "pub", "nightclub", "music_venue"}), "nightlife"),
    ("amenity", frozenset({"restaurant", "fast_food"}), "restaurant"),
    ("amenity", frozenset({"cafe", "ice_cream"}), "cafe"),
    ("shop", frozenset({"pastry"}), "cafe"),
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
    ("place", frozenset({"square"}), "landmark"),
]

# Small memorials that are not worth a walk.
SKIP_MEMORIAL_TYPES = frozenset({"plaque", "blue_plaque", "stolperstein"})
SKIP_ACCESS = frozenset({"private", "no"})
# Closed, as a word: English, Portuguese, German, Spanish, Catalan, French, Italian, Dutch,
# Czech, Polish, Hungarian, Swedish, Danish, Norwegian, Turkish and Greek.
_CLOSED = (
    r"closed|fechad[ao]s?|encerrad[ao]s?|geschlossen|cerrad[ao]s?|tancats?|tancad[ae]s?"
    r"|fermée?s?|chius[oaie]|gesloten|zavřen[oaáéý]|zamknięt[aey]|nieczynn[aey]|zárva|bezárt"
    r"|stängt|stängda?|lukket|stengt|kapal[ıi]|kapand[ıi]|κλειστ(?:ό|ή|ά|ός|ο|η|α|ος)"
)
# ...and in the scripts written without spaces between words: Japanese, Chinese, Korean
# and Thai ("（閉店）", "(2023年閉店)").
_CLOSED_UNSPACED = r"閉店|閉業|休業中|歇業|結業|已關閉|已关闭|폐업|폐점|ปิดกิจการ|ปิดถาวร"
# Places OSM still maps after they closed, named like "Alma (closed)", "Solmar (Fechada)",
# "Kantine (bis vsl 2027 geschlossen)".
CLOSED_NAME = re.compile(
    rf"[(（](?:(?:[^()（）]*\s)?(?:{_CLOSED})|[^()（）]*(?:{_CLOSED_UNSPACED}))[)）]",
    re.IGNORECASE,
)
# ...or venues with opening hours that say so ("Fechado permanentemente", "Cerrado
# temporalmente", "vorübergehend geschlossen"), unlike "Su off" or "Mo geschlossen".
_TEMPORARILY = (
    r"vorübergehend|temporär|zurzeit|dauerhaft|bis auf weiteres|permanent|permanentemente"
    r"|definitivamente|temporaneamente|temporairement|définitivement|tijdelijk|dočasně"
    r"|tymczasowo|czasowo|ideiglenesen|tillfälligt|midlertidig|midlertidigt|geçici olarak"
    r"|προσωρινά"
)
CLOSED_HOURS = re.compile(
    rf"\s*(?:(?:{_TEMPORARILY})\s+)?(?:(?:off|{_CLOSED})\b|{_CLOSED_UNSPACED})",
    re.IGNORECASE,
)


# The OSM tags a place keeps in the database: those the app reads (category, indoor or
# outdoor, hours, venue details, Wikimedia links, names to search by and to go by, which
# app.ingest.enrich reads again: display_name). The rest (addresses,
# survey dates, names in other languages) is half the size of a place's tags, which the free
# database plan has little room for. The Overpass cache (data/raw) keeps every tag: a
# re-import brings back any the app starts to read. test_osm checks that it reads no other.
KEPT_TAGS = frozenset(
    {
        "name",
        "name:en",
        "int_name",
        "tourism",
        "amenity",
        "historic",
        "leisure",
        "shop",
        "place",
        "building",
        "memorial",
        "artwork_type",
        "castle_type",
        "indoor",
        "covered",
        "lit",
        "access",
        "opening_hours",
        "website",
        "contact:website",
        "phone",
        "contact:phone",
        "cuisine",
        "outdoor_seating",
        "wikidata",
        "wikipedia",
        "wikimedia_commons",
        "image",
        "description",
        "description:en",
    }
)
KEPT_TAG_PREFIXES = ("diet:",)


def kept_tags(tags: dict[str, str]) -> dict[str, str]:
    """The tags a place keeps in the database (KEPT_TAGS, and romanized names)."""
    return {
        k: v
        for k, v in tags.items()
        if k in KEPT_TAGS or k.startswith(KEPT_TAG_PREFIXES) or romanized_name(k)
    }


def romanized_name(key: str) -> bool:
    """A tag with a name in Latin letters: name:ja-Latn, name:ko-Latn, name:ja_rm."""
    return key.startswith("name:") and key.endswith(("-Latn", "_rm"))


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


# Overpass numbers the area of OSM relation N as this plus N.
OVERPASS_AREA_BASE = 3_600_000_000


def build_query(bbox: BBox, timeout_s: int = 180, boundary: int | None = None) -> str:
    """Places in `bbox`, and inside the OSM relation `boundary` too when there is one."""
    values_by_key: dict[str, set[str]] = defaultdict(set)
    for key, values, _ in CATEGORY_RULES:
        values_by_key[key] |= values

    area = f"({bbox.south},{bbox.west},{bbox.north},{bbox.east})"
    if boundary is not None:
        area += f"(area:{OVERPASS_AREA_BASE + boundary})"
    selectors = "\n".join(
        f'  nwr["{key}"~"^({"|".join(sorted(values))})$"]["name"]{area};'
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
            payload = response.json()
            # A query that runs out of time or memory still answers 200, with only part of
            # the elements and a remark that says so.
            if "runtime error" in payload.get("remark", ""):
                raise ValueError(payload["remark"])
            return cast(list[dict[str, Any]], payload["elements"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last_error = exc
    raise RuntimeError("All Overpass mirrors failed") from last_error


def categorize(tags: dict[str, str]) -> str | None:
    for key, values, category in CATEGORY_RULES:
        if tags.get(key) in values:
            # Artworks are statues and murals, but for buildings that open to visitors.
            if key == "tourism" and category == "monument" and open_building(tags):
                return "landmark"
            return category
    return None


def in_latin_script(text: str) -> bool:
    """Whether every letter of `text` is a Latin one (accented or not, ª and º too)."""
    return all(
        not ch.isalpha() or ord(ch) <= 0x24F or unicodedata.name(ch, "").startswith("LATIN")
        for ch in text
    )


def display_name(tags: dict[str, str]) -> str:
    """The name a place goes by: its OSM name, or for a name in another script ("浅草寺",
    "Ακρόπολη", "香港文化中心 Hong Kong Cultural Centre") its English name or a
    romanization when OSM has one ("Sensō-ji"). The OSM name stays in the tags."""
    name = tags.get("name", "").strip()
    if in_latin_script(name):
        return name
    for key in ("name:en", "int_name", *sorted(filter(romanized_name, tags))):
        other = tags.get(key, "").strip()
        if other and in_latin_script(other) and any(ch.isalpha() for ch in other):
            return other
    return name


def _is_worth_visiting(name: str, category: str, tags: dict[str, str]) -> bool:
    # The OSM name tells a closed place too when it goes by another one ("喫茶（閉店）").
    names = (name, tags.get("name", ""))
    if tags.get("access") in SKIP_ACCESS or any(CLOSED_NAME.search(n) for n in names):
        return False
    if category in VENUE_CATEGORIES:
        return not CLOSED_HOURS.match(tags.get("opening_hours", ""))
    return tags.get("memorial") not in SKIP_MEMORIAL_TYPES


def parse_elements(elements: list[dict[str, Any]]) -> list[PlaceRecord]:
    records: list[PlaceRecord] = []
    for element in elements:
        tags: dict[str, str] = element.get("tags", {})
        name = display_name(tags)
        category = categorize(tags)
        if not name or category is None or not _is_worth_visiting(name, category, tags):
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
