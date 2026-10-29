"""Candidate generation: rank a city's places for a trip before the LLM picks from them."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, Float, case, cast, func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import EVENING_CATEGORIES, VisitHours, is_outdoor, visit_hours
from app.db.models import Category, Place
from app.optimizer.geometry import LatLon
from app.repositories.search import name_matches

# Score weights. Notability (Wikidata/Wikipedia) keeps 700 street-art pieces from
# drowning out the castle; explicit wishes outrank everything.
WEIGHT_WIKIDATA = 2.0
WEIGHT_WIKIPEDIA = 1.0
WEIGHT_INTEREST = 2.5
WEIGHT_KEYWORD = 4.0
# Closeness to an anchor (the hotel, a must-visit place): the full weight at the anchor,
# fading linearly to nothing at the proximity radius.
WEIGHT_PROXIMITY = 3.0
DEFAULT_PROXIMITY_RADIUS_M = 2500.0
HINT_MAX_CHARS = 80


@dataclass(frozen=True)
class Candidate:
    id: int
    name: str
    category: str
    score: float
    hint: str | None
    lat: float
    lon: float
    # Metres to the nearest anchor; None when the search had no anchors.
    distance_m: float | None = None
    # Visited in the open air (app.catalog.is_outdoor).
    outdoor: bool = False
    # When it can be visited (app.catalog.visit_hours).
    hours: VisitHours = "any"
    # Its OSM opening hours, as written (app.osm_hours reads them).
    opening_hours: str | None = None


def _hint(name: str, tags: dict[str, str]) -> str | None:
    english = tags.get("name:en")
    hint = english if english and english != name else tags.get("description")
    return hint[:HINT_MAX_CHARS] if hint else None


def _as_score(condition: ColumnElement[bool], weight: float) -> ColumnElement[Any]:
    return case((condition, weight), else_=0.0)


def _may_open_at_night() -> ColumnElement[bool]:
    """In SQL, a superset of the places app.catalog.visit_hours opens after 20:00: evening
    venues, lit places, squares, and places with opening hours (which may run late)."""
    return or_(
        Category.slug.in_(EVENING_CATEGORIES),
        Place.tags["lit"].astext == "yes",
        Place.tags["place"].astext == "square",
        Place.tags.has_key("opening_hours"),
    )


def _geography(point: LatLon) -> ColumnElement[Any]:
    return cast(func.ST_SetSRID(func.ST_MakePoint(point.lon, point.lat), 4326), Geography)


def _select(score: ColumnElement[Any], distance: ColumnElement[Any]) -> Any:
    point = func.geometry(Place.geom)
    return select(
        Place.id,
        Place.name,
        Category.slug.label("category"),
        Place.tags,
        score.label("score"),
        func.ST_Y(point).label("lat"),
        func.ST_X(point).label("lon"),
        distance.label("distance_m"),
    ).join(Category)


def _to_candidate(row: Any) -> Candidate:
    return Candidate(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        score=row["score"],
        hint=_hint(row["name"], row["tags"]),
        lat=row["lat"],
        lon=row["lon"],
        distance_m=row["distance_m"],
        outdoor=is_outdoor(row["category"], row["tags"]),
        hours=visit_hours(row["category"], row["tags"]),
        opening_hours=row["tags"].get("opening_hours"),
    )


async def find_candidates(
    session: AsyncSession,
    *,
    city: str,
    interests: Sequence[str] = (),
    avoid: Sequence[str] = (),
    keywords: Sequence[str] = (),
    anchors: Sequence[LatLon] = (),
    proximity_radius_m: float = DEFAULT_PROXIMITY_RADIUS_M,
    exclude_ids: Collection[int] = (),
    limit: int = 60,
    exclude_categories: Sequence[str] = (),
    open_at_night: bool = False,
) -> list[Candidate]:
    """`exclude_categories` leaves those out even when named (unlike `avoid`). `open_at_night`
    keeps only places that can be visited after 20:00 (lit squares, places open late)."""
    keyword_match = name_matches(keywords)
    score = (
        _as_score(Place.wikidata.is_not(None), WEIGHT_WIKIDATA)
        + _as_score(Place.tags.has_key("wikipedia"), WEIGHT_WIKIPEDIA)
        + _as_score(Category.slug.in_(interests), WEIGHT_INTEREST)
        + _as_score(keyword_match, WEIGHT_KEYWORD)
    )
    distance: ColumnElement[Any] = null()
    if anchors:
        distance = func.least(*(func.ST_Distance(Place.geom, _geography(a)) for a in anchors))
        closeness = func.greatest(0.0, 1.0 - distance / proximity_radius_m)
        score = score + WEIGHT_PROXIMITY * closeness
    score = score.cast(Float)

    conditions = [Place.city == city]
    if avoid:
        # An explicitly named place survives even if its category is avoided.
        conditions.append(or_(Category.slug.not_in(avoid), keyword_match))
    if exclude_ids:
        conditions.append(Place.id.not_in(exclude_ids))
    if exclude_categories:
        conditions.append(Category.slug.not_in(exclude_categories))
    if open_at_night:
        conditions.append(_may_open_at_night())

    # Ties go to the closer place, then to the lower id (stable results).
    order_by = [score.desc(), *([distance] if anchors else []), Place.id]
    stmt = _select(score, distance).where(*conditions).order_by(*order_by)
    if not open_at_night:
        return [_to_candidate(row) for row in (await session.execute(stmt.limit(limit))).mappings()]
    # The exact rule narrows the superset here, so the limit comes after it (the superset is
    # small: a few hundred places in Lisbon).
    found = map(_to_candidate, (await session.execute(stmt)).mappings())
    return [c for c in found if c.hours in ("night", "any")][:limit]


async def get_candidates(
    session: AsyncSession, place_ids: Sequence[int], *, city: str
) -> list[Candidate]:
    """The given places of a city, in the given order; unknown ids are left out."""
    if not place_ids:
        return []
    stmt = _select(cast(0.0, Float), null()).where(Place.city == city, Place.id.in_(place_ids))
    found = {c.id: c for c in map(_to_candidate, (await session.execute(stmt)).mappings())}
    return [found[i] for i in dict.fromkeys(place_ids) if i in found]
