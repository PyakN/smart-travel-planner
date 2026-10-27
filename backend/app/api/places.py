from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import SessionDep
from app.geo import BBox
from app.repositories import places as repo
from app.repositories.places import Near, PlaceFilters
from app.schemas.place import CategoryOut, PlaceOut, PlacePage

router = APIRouter(tags=["places"])

MAX_RADIUS_M = 20_000


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def parse_bbox(raw: str) -> BBox:
    try:
        west, south, east, north = (float(part) for part in raw.split(","))
    except ValueError:
        raise _invalid("bbox must be 'west,south,east,north'") from None
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise _invalid("bbox must satisfy west < east and south < north within WGS84 range")
    return BBox(south=south, west=west, north=north, east=east)


def place_filters(
    city: str | None = None,
    q: Annotated[
        str | None,
        Query(min_length=2, max_length=100, description="Name contains (accents ignored)"),
    ] = None,
    category: Annotated[list[str] | None, Query(description="Repeat for several")] = None,
    bbox: Annotated[str | None, Query(description="west,south,east,north")] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_m: Annotated[float | None, Query(gt=0, le=MAX_RADIUS_M)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlaceFilters:
    near_params = (lat, lon, radius_m)
    if any(p is not None for p in near_params) and any(p is None for p in near_params):
        raise _invalid("lat, lon and radius_m must be given together")
    near = Near(lat, lon, radius_m) if lat is not None and lon is not None and radius_m else None
    return PlaceFilters(
        city=city,
        q=q.strip() or None if q else None,
        categories=tuple(category or ()),
        bbox=parse_bbox(bbox) if bbox else None,
        near=near,
        limit=limit,
        offset=offset,
    )


@router.get("/places")
async def search_places(
    session: SessionDep, filters: Annotated[PlaceFilters, Depends(place_filters)]
) -> PlacePage:
    items, total = await repo.search_places(session, filters)
    return PlacePage(items=items, total=total, limit=filters.limit, offset=filters.offset)


@router.get("/places/{place_id}")
async def get_place(session: SessionDep, place_id: int) -> PlaceOut:
    place = await repo.get_place(session, place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "place not found")
    return place


@router.get("/categories")
async def list_categories(session: SessionDep, city: str | None = None) -> list[CategoryOut]:
    return await repo.list_categories(session, city)
