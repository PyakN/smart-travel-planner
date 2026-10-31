"""Candidate generation: rank a city's places for a trip before the LLM picks from them."""

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, Float, Text, case, cast, func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import EVENING_CATEGORIES, VisitHours, is_outdoor, visit_hours
from app.db.models import Category, Place
from app.optimizer.geometry import LatLon
from app.repositories.search import name_matches

# Score weights. Fame keeps 700 street-art pieces from drowning out the castle, and the
# Sagrada Família from tying with hundreds of churches; explicit wishes outrank everything.
# Fame grows with the log of the Wikipedia languages that cover a place, to the full weight
# at FAME_FULL_LANGUAGES: 1 language gives 0.6, 10 give 2.1, 30 give 3, 100 give 4. So a
# world-famous place outranks an obscure one of the traveller's interests, and a known one
# of their interests (5+ languages) outranks any other.
WEIGHT_FAME = 4.0
FAME_FULL_LANGUAGES = 100
WEIGHT_INTEREST = 2.5
WEIGHT_KEYWORD = 5.0
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
    # Wikipedia languages that cover it, and whether it is one of the city's most famous
    # places (find_candidates' `famous`).
    wikipedia_languages: int = 0
    famous: bool = False


def _hint(name: str, tags: dict[str, str]) -> str | None:
    english = tags.get("name:en")
    hint = english if english and english != name else tags.get("description")
    return hint[:HINT_MAX_CHARS] if hint else None


def _as_score(condition: ColumnElement[bool], weight: float) -> ColumnElement[Any]:
    return case((condition, weight), else_=0.0)


def _fame() -> ColumnElement[Any]:
    share = func.ln(1 + Place.wikipedia_languages) / math.log1p(FAME_FULL_LANGUAGES)
    return WEIGHT_FAME * func.least(1.0, share)


def _order(columns: Any, anchors: Sequence[LatLon]) -> list[Any]:
    """Best score first; ties go to the closer place, then to the lower id (stable results)."""
    return [columns.score.desc(), *([columns.distance_m] if anchors else []), columns.id]


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
        Place.wikipedia_languages,
        score.label("score"),
        func.ST_Y(point).label("lat"),
        func.ST_X(point).label("lon"),
        distance.label("distance_m"),
    ).join(Category)


def _to_candidate(row: Any, famous: int = 0) -> Candidate:
    fame_rank = row.get("fame_rank")
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
        wikipedia_languages=row["wikipedia_languages"],
        famous=fame_rank is not None and fame_rank <= famous,
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
    famous: int = 0,
) -> list[Candidate]:
    """`exclude_categories` leaves those out even when named (unlike `avoid`). `open_at_night`
    keeps only places that can be visited after 20:00 (lit squares, places open late).
    `famous` adds the city's most famous places to the `limit` best ranked, however the
    request ranks them: its interests are a guess at categories, and the Sagrada Família is
    a church on a Gaudí day, Berlin's TV Tower an attraction for a view over the city."""
    keyword_match = name_matches(keywords)
    fame = _fame()
    score = (
        fame
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

    # One place per Wikidata item, the best ranked: OSM maps some sights in pieces that all
    # link the whole (24 stretches of Lisbon's aqueduct, five of La Rambla), and their fame
    # would fill the list with copies.
    item = func.coalesce(Place.wikidata, cast(Place.id, Text))
    order_by = [score.desc(), *([distance] if anchors else []), Place.id]
    nth_of_item = func.row_number().over(partition_by=item, order_by=order_by)
    rows = (
        _select(score, distance)
        .add_columns(fame.label("fame"), nth_of_item.label("nth"))
        .where(*conditions)
        .subquery()
    )
    by_score = _order(rows.c, anchors)
    firsts = (
        select(
            rows,
            func.row_number().over(order_by=by_score).label("rank"),
            func.row_number().over(order_by=[rows.c.fame.desc(), *by_score]).label("fame_rank"),
        )
        .where(rows.c.nth == 1)
        .subquery()
    )
    stmt = select(firsts).order_by(*_order(firsts.c, anchors))
    if not open_at_night:
        stmt = stmt.where(or_(firsts.c.rank <= limit, firsts.c.fame_rank <= famous))
        return [_to_candidate(row, famous) for row in (await session.execute(stmt)).mappings()]
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
