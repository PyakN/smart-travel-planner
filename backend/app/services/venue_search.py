"""Places to eat and drink near a point (GET /venues): food (restaurants, fast food, cafés,
ice cream, pastry shops) or drinks (bars, pubs, clubs), with what OpenStreetMap knows of
them: cuisine, diets, outdoor seating and opening hours, read to tell whether each is open
now and when the traveller gets there. OSM has no ratings or prices.

Closest first, by the minute of walking; among venues as close, the ones with the most
complete data come first, as they are the ones a traveller can judge.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import get_args

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.cities import CITIES
from app.optimizer.distance import DETOUR_FACTOR
from app.optimizer.planner import WALKING_M_PER_MIN
from app.osm_hours import next_change, open_state, read_hours
from app.repositories.places import Near, NearbyPlace, places_near
from app.schemas.venue import (
    CuisineCount,
    DietLevel,
    VenueKind,
    VenueOut,
    VenuePage,
    VenueType,
)

KIND_CATEGORIES: dict[VenueKind, tuple[str, ...]] = {
    "food": ("restaurant", "cafe"),
    "drinks": ("nightlife",),
}
ALL_CATEGORIES = tuple(c for categories in KIND_CATEGORIES.values() for c in categories)
VENUE_TYPES: dict[str, VenueType] = {t: t for t in get_args(VenueType)}
# For venues whose tags say no more than their category.
CATEGORY_TYPES: dict[str, VenueType] = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "nightlife": "bar",
}
# A usual stay, which the traveller can change: a coffee and a dinner differ a lot.
STAY_MIN: dict[VenueType, int] = {
    "restaurant": 75,
    "fast_food": 30,
    "cafe": 30,
    "ice_cream": 15,
    "pastry": 30,
    "bar": 60,
    "pub": 60,
    "nightclub": 120,
    "music_venue": 90,
}
# OSM `diet:*` keys worth showing, and the values that mean the diet is catered for.
DIETS = ("vegetarian", "vegan", "gluten_free", "halal", "kosher")
DIET_LEVELS: dict[str, DietLevel] = {"yes": "yes", "only": "only"}
# Opening or closing times further ahead are not worth a clock time.
CHANGE_HORIZON = timedelta(days=1)


@dataclass(frozen=True)
class VenueFilters:
    near: Near
    kind: VenueKind | None = None
    cuisine: str | None = None
    vegetarian: bool = False
    vegan: bool = False
    # Open by the time the traveller walks there.
    open_now: bool = False
    outdoor_seating: bool = False
    limit: int = 30


def normalize_cuisine(value: str) -> str:
    """OSM cuisine values are lowercase with underscores: "Coffee shop" -> "coffee_shop"."""
    return "_".join(value.lower().split())


def _venue_type(place: NearbyPlace) -> VenueType:
    for key in ("amenity", "shop"):
        if venue_type := VENUE_TYPES.get(place.tags.get(key, "")):
            return venue_type
    return CATEGORY_TYPES.get(place.category, "restaurant")


def _cuisines(tags: Mapping[str, str]) -> list[str]:
    values = (normalize_cuisine(c) for c in tags.get("cuisine", "").split(";"))
    return list(dict.fromkeys(c for c in values if c))


def _diets(tags: Mapping[str, str], cuisines: Sequence[str]) -> dict[str, DietLevel]:
    diets: dict[str, DietLevel] = {}
    for diet in DIETS:
        if level := DIET_LEVELS.get(tags.get(f"diet:{diet}", "")):
            diets[diet] = level
    # A vegetarian or vegan restaurant (cuisine=vegan) serves nothing else.
    for diet in ("vegetarian", "vegan"):
        if diet in cuisines:
            diets[diet] = "only"
    # Vegan food is vegetarian.
    vegan = diets.get("vegan")
    if vegan and diets.get("vegetarian") != "only":
        diets["vegetarian"] = vegan
    return diets


def _yes_no(value: str | None) -> bool | None:
    return {"yes": True, "no": False}.get(value or "")


def walk_minutes(distance_m: float) -> int:
    """Minutes on foot for a straight-line distance, with the usual detour of streets."""
    return max(1, round(distance_m * DETOUR_FACTOR / WALKING_M_PER_MIN))


def describe_venue(place: NearbyPlace, now: datetime) -> VenueOut:
    city = CITIES.get(place.city)
    hours = read_hours(place.opening_hours, city, place.lat, place.lon) if city else None
    walk = walk_minutes(place.distance_m)
    change = next_change(hours, now)
    cuisines = _cuisines(place.tags)
    venue_type = _venue_type(place)
    return VenueOut(
        id=place.id,
        name=place.name,
        category=place.category,
        venue_type=venue_type,
        lat=place.lat,
        lon=place.lon,
        distance_m=round(place.distance_m, 1),
        walk_min=walk,
        cuisines=cuisines,
        diets=_diets(place.tags, cuisines),
        outdoor_seating=_yes_no(place.tags.get("outdoor_seating")),
        opening_hours=place.opening_hours,
        open_now=open_state(hours, now),
        open_on_arrival=open_state(hours, now + timedelta(minutes=walk)),
        changes_at=f"{change:%H:%M}" if change and change - now <= CHANGE_HORIZON else None,
        website=place.website,
        phone=place.tags.get("phone") or place.tags.get("contact:phone"),
        stay_min=STAY_MIN[venue_type],
    )


def _completeness(venue: VenueOut) -> int:
    """How much a traveller can tell about a venue before going."""
    return sum(
        (
            venue.open_now != "unknown",
            bool(venue.cuisines),
            bool(venue.diets),
            venue.outdoor_seating is not None,
            venue.website is not None,
            venue.phone is not None,
        )
    )


def _passes(venue: VenueOut, filters: VenueFilters) -> bool:
    """Every filter but the cuisine."""
    return not (
        (filters.vegetarian and "vegetarian" not in venue.diets)
        or (filters.vegan and "vegan" not in venue.diets)
        or (filters.open_now and venue.open_on_arrival != "open")
        or (filters.outdoor_seating and venue.outdoor_seating is not True)
    )


def venue_page(venues: Sequence[VenueOut], filters: VenueFilters) -> VenuePage:
    """The venues that match, in order, and the cuisines to choose from: those of the venues
    the other filters leave."""
    others = [v for v in venues if _passes(v, filters)]
    counts = Counter(c for v in others for c in v.cuisines)
    matching = [v for v in others if not filters.cuisine or filters.cuisine in v.cuisines]
    matching.sort(key=lambda v: (v.walk_min, -_completeness(v), v.distance_m, v.id))
    return VenuePage(
        items=matching[: filters.limit],
        total=len(matching),
        cuisines=[
            CuisineCount(cuisine=cuisine, count=count)
            for cuisine, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )


async def search_venues(session: AsyncSession, filters: VenueFilters, now: datetime) -> VenuePage:
    categories = KIND_CATEGORIES[filters.kind] if filters.kind else ALL_CATEGORIES
    places = await places_near(session, filters.near, categories)
    return venue_page([describe_venue(p, now) for p in places], filters)
