from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import NowDep, SessionDep
from app.repositories.places import Near
from app.schemas.venue import VenueKind, VenuePage
from app.services.venue_search import VenueFilters, normalize_cuisine, search_venues

router = APIRouter(tags=["venues"])

MIN_RADIUS_M = 250
MAX_RADIUS_M = 2000


def venue_filters(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[int, Query(ge=MIN_RADIUS_M, le=MAX_RADIUS_M)] = 500,
    kind: Annotated[
        VenueKind | None,
        Query(description="food: restaurants, cafés...; drinks: bars, pubs, clubs"),
    ] = None,
    cuisine: Annotated[
        str | None, Query(min_length=2, max_length=50, description='e.g. "portuguese"')
    ] = None,
    vegetarian: Annotated[bool, Query(description="Vegetarian (or vegan) food")] = False,
    vegan: bool = False,
    open_now: Annotated[
        bool, Query(description="Open by the time you walk there from the point")
    ] = False,
    outdoor_seating: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> VenueFilters:
    return VenueFilters(
        near=Near(lat, lon, radius_m),
        kind=kind,
        cuisine=normalize_cuisine(cuisine) if cuisine else None,
        vegetarian=vegetarian,
        vegan=vegan,
        open_now=open_now,
        outdoor_seating=outdoor_seating,
        limit=limit,
    )


@router.get("/venues")
async def find_venues(
    session: SessionDep,
    now: NowDep,
    filters: Annotated[VenueFilters, Depends(venue_filters)],
    at: Annotated[
        datetime | None,
        Query(
            description="When you set off from the point, in the city's time without an "
            'offset (e.g. "2026-11-05T13:10"): a later stop of a day ahead. Default: now'
        ),
    ] = None,
) -> VenuePage:
    """Places to eat and drink near a point (data from OpenStreetMap), closest first, then
    the ones with the most complete data. Each says whether it is open now (or `at`) and
    when you get there, from its opening hours; hours that cannot be read are unknown."""
    return await search_venues(session, filters, at or now)
