from pydantic import BaseModel


class CategoryOut(BaseModel):
    slug: str
    name: str
    place_count: int


class PlaceOut(BaseModel):
    id: int
    name: str
    category: str
    lat: float
    lon: float
    wikidata: str | None
    opening_hours: str | None
    website: str | None
    # Only set when searching around a point.
    distance_m: float | None = None


class PlacePage(BaseModel):
    items: list[PlaceOut]
    total: int
    limit: int
    offset: int
