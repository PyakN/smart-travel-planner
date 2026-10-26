"""Candidate generation: rank a city's places for a trip before the LLM picks from them."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Float, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category, Place

# Score weights. Notability (Wikidata/Wikipedia) keeps 700 street-art pieces from
# drowning out the castle; explicit wishes outrank everything.
WEIGHT_WIKIDATA = 2.0
WEIGHT_WIKIPEDIA = 1.0
WEIGHT_INTEREST = 2.5
WEIGHT_KEYWORD = 4.0
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


def _like_pattern(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _keyword_match(keywords: Sequence[str]) -> ColumnElement[bool]:
    if not keywords:
        return false()
    haystacks = [Place.name, Place.tags["name:en"].astext]
    return or_(
        *(
            func.unaccent(haystack).ilike(func.unaccent(_like_pattern(keyword)), escape="\\")
            for keyword in keywords
            for haystack in haystacks
        )
    )


def _hint(name: str, tags: dict[str, str]) -> str | None:
    english = tags.get("name:en")
    hint = english if english and english != name else tags.get("description")
    return hint[:HINT_MAX_CHARS] if hint else None


def _as_score(condition: ColumnElement[bool], weight: float) -> ColumnElement[Any]:
    return case((condition, weight), else_=0.0)


async def find_candidates(
    session: AsyncSession,
    *,
    city: str,
    interests: Sequence[str] = (),
    avoid: Sequence[str] = (),
    keywords: Sequence[str] = (),
    limit: int = 60,
) -> list[Candidate]:
    keyword_match = _keyword_match(keywords)
    score = (
        _as_score(Place.wikidata.is_not(None), WEIGHT_WIKIDATA)
        + _as_score(Place.tags.has_key("wikipedia"), WEIGHT_WIKIPEDIA)
        + _as_score(Category.slug.in_(interests), WEIGHT_INTEREST)
        + _as_score(keyword_match, WEIGHT_KEYWORD)
    ).cast(Float)

    conditions = [Place.city == city]
    if avoid:
        # An explicitly named place survives even if its category is avoided.
        conditions.append(or_(Category.slug.not_in(avoid), keyword_match))

    point = func.geometry(Place.geom)
    stmt = (
        select(
            Place.id,
            Place.name,
            Category.slug.label("category"),
            Place.tags,
            score.label("score"),
            func.ST_Y(point).label("lat"),
            func.ST_X(point).label("lon"),
        )
        .join(Category)
        .where(*conditions)
        .order_by(score.desc(), Place.id)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).mappings()
    return [
        Candidate(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            score=row["score"],
            hint=_hint(row["name"], row["tags"]),
            lat=row["lat"],
            lon=row["lon"],
        )
        for row in rows
    ]
