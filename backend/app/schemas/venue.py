"""Places to eat and drink near a point (GET /venues)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.osm_hours import OpenState

# Food: restaurants, fast food, cafés, ice cream and pastry shops. Drinks: bars, pubs, clubs
# and live music venues.
VenueKind = Literal["food", "drinks"]
# The OSM amenity (or shop) a venue is.
VenueType = Literal[
    "restaurant",
    "fast_food",
    "cafe",
    "ice_cream",
    "pastry",
    "bar",
    "pub",
    "nightclub",
    "music_venue",
]
# "only": nothing else is served (a vegetarian restaurant).
DietLevel = Literal["yes", "only"]


class VenueOut(BaseModel):
    id: int = Field(description="Place id: add it to a day with POST /trips/{id}/edit")
    name: str
    category: str = Field(description="restaurant, cafe or nightlife")
    venue_type: VenueType
    lat: float
    lon: float
    distance_m: float = Field(description="Straight-line distance from the point")
    walk_min: int = Field(description="Estimated walk from the point")
    cuisines: list[str] = Field(description='OSM cuisine values, e.g. "portuguese", "pizza"')
    diets: dict[str, DietLevel] = Field(
        description='Diets catered for, e.g. {"vegetarian": "only", "vegan": "yes"}'
    )
    outdoor_seating: bool | None = Field(description="None when unknown")
    opening_hours: str | None = Field(description="OSM opening_hours syntax, as mapped")
    open_now: OpenState
    open_on_arrival: OpenState = Field(description="When the walk from the point ends")
    changes_at: str | None = Field(
        description='"HH:MM": when it opens or closes next, if within a day'
    )
    website: str | None
    phone: str | None
    stay_min: int = Field(description="A usual stay: café 30 min, bar 60, restaurant 75")


class CuisineCount(BaseModel):
    cuisine: str
    count: int


class VenuePage(BaseModel):
    items: list[VenueOut]
    total: int = Field(description="Venues that match, before the limit")
    cuisines: list[CuisineCount] = Field(
        description="Cuisines in range that the other filters leave, most common first"
    )
