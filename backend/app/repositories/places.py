from dataclasses import dataclass
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, cast, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import SQLCoreOperations

from app.db.models import Category, Place
from app.geo import BBox
from app.schemas.place import CategoryOut, PlaceOut


@dataclass(frozen=True)
class Near:
    lat: float
    lon: float
    radius_m: float


@dataclass(frozen=True)
class PlaceFilters:
    city: str | None = None
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

    # Closest first around a point; otherwise well-known places (with Wikidata) first.
    order_by = (
        [distance, Place.id]
        if distance is not None
        else [Place.wikidata.is_(None), Place.name, Place.id]
    )
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
