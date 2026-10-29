from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, cast, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import SQLCoreOperations

from app.db.models import Category, Place
from app.geo import BBox
from app.repositories.search import like_pattern, name_matches
from app.schemas.place import CategoryOut, PlaceOut


@dataclass(frozen=True)
class Near:
    lat: float
    lon: float
    radius_m: float


@dataclass(frozen=True)
class PlaceFilters:
    city: str | None = None
    # Accent-insensitive name search (local or English name).
    q: str | None = None
    categories: tuple[str, ...] = ()
    bbox: BBox | None = None
    near: Near | None = None
    limit: int = 50
    offset: int = 0


def _point(lat: float, lon: float) -> ColumnElement[Any]:
    return cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)


def _place_columns() -> list[SQLCoreOperations[Any]]:
    point = func.geometry(Place.geom)
    return [
        Place.id,
        Place.name,
        Category.slug.label("category"),
        func.ST_Y(point).label("lat"),
        func.ST_X(point).label("lon"),
        Place.wikidata,
        Place.opening_hours,
        Place.website,
    ]


async def search_places(session: AsyncSession, filters: PlaceFilters) -> tuple[list[PlaceOut], int]:
    conditions: list[ColumnElement[bool]] = []
    if filters.city:
        conditions.append(Place.city == filters.city)
    if filters.q:
        conditions.append(name_matches([filters.q]))
    if filters.categories:
        conditions.append(Category.slug.in_(filters.categories))
    if filters.bbox:
        b = filters.bbox
        envelope = cast(func.ST_MakeEnvelope(b.west, b.south, b.east, b.north, 4326), Geography)
        conditions.append(func.ST_Intersects(Place.geom, envelope))

    distance: ColumnElement[Any] | None = None
    if filters.near:
        point = _point(filters.near.lat, filters.near.lon)
        conditions.append(func.ST_DWithin(Place.geom, point, filters.near.radius_m))
        distance = func.ST_Distance(Place.geom, point)

    total = await session.scalar(
        select(func.count()).select_from(Place).join(Category).where(*conditions)
    )

    # Closest first around a point; otherwise well-known places (with Wikidata) first,
    # after names that start with the search text.
    order_by: list[SQLCoreOperations[Any]] = [Place.wikidata.is_(None), Place.name, Place.id]
    if distance is not None:
        order_by = [distance, Place.id]
    elif filters.q:
        starts = func.unaccent(Place.name).ilike(
            func.unaccent(like_pattern(filters.q, prefix=True)), escape="\\"
        )
        order_by.insert(0, starts.desc())
    distance_column = (distance if distance is not None else null()).label("distance_m")
    stmt = (
        select(*_place_columns(), distance_column)
        .join(Category)
        .where(*conditions)
        .order_by(*order_by)
        .limit(filters.limit)
        .offset(filters.offset)
    )
    rows = (await session.execute(stmt)).mappings()
    return [PlaceOut.model_validate(dict(row)) for row in rows], total or 0


async def get_place(session: AsyncSession, place_id: int) -> PlaceOut | None:
    stmt = select(*_place_columns()).join(Category).where(Place.id == place_id)
    row = (await session.execute(stmt)).mappings().first()
    return PlaceOut.model_validate(dict(row)) if row else None


@dataclass(frozen=True)
class PlaceDetails:
    """What a stop card shows besides the schedule."""

    description: str | None
    opening_hours: str | None
    website: str | None
    image_url: str | None
    image_page_url: str | None
    image_credit: str | None


async def place_details(
    session: AsyncSession, place_ids: Collection[int]
) -> dict[int, PlaceDetails]:
    if not place_ids:
        return {}
    stmt = select(
        Place.id,
        Place.description,
        Place.opening_hours,
        Place.website,
        Place.image_url,
        Place.image_page_url,
        Place.image_credit,
    ).where(Place.id.in_(place_ids))
    return {
        row["id"]: PlaceDetails(**{k: v for k, v in row.items() if k != "id"})
        for row in (await session.execute(stmt)).mappings()
    }


@dataclass(frozen=True)
class NearbyPlace:
    """A place around a point, with its OSM tags."""

    id: int
    name: str
    city: str
    category: str
    lat: float
    lon: float
    tags: dict[str, str]
    website: str | None
    opening_hours: str | None
    distance_m: float


async def places_near(
    session: AsyncSession, near: Near, categories: Collection[str]
) -> list[NearbyPlace]:
    """Every place of `categories` within the radius, closest first."""
    point = _point(near.lat, near.lon)
    distance = func.ST_Distance(Place.geom, point)
    geom = func.geometry(Place.geom)
    stmt = (
        select(
            Place.id,
            Place.name,
            Place.city,
            Category.slug.label("category"),
            func.ST_Y(geom).label("lat"),
            func.ST_X(geom).label("lon"),
            Place.tags,
            Place.website,
            Place.opening_hours,
            distance.label("distance_m"),
        )
        .join(Category)
        .where(Category.slug.in_(categories), func.ST_DWithin(Place.geom, point, near.radius_m))
        .order_by(distance, Place.id)
    )
    return [NearbyPlace(**row) for row in (await session.execute(stmt)).mappings()]


async def list_categories(session: AsyncSession, city: str | None = None) -> list[CategoryOut]:
    join_on = Place.category_id == Category.id
    if city:
        join_on = join_on & (Place.city == city)
    stmt = (
        select(Category.slug, Category.name, func.count(Place.id).label("place_count"))
        .outerjoin(Place, join_on)
        .group_by(Category.id)
        .order_by(Category.id)
    )
    rows = (await session.execute(stmt)).mappings()
    return [CategoryOut.model_validate(dict(row)) for row in rows]
