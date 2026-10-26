from pydantic import BaseModel, Field

from app.schemas.trip import MAX_REQUEST_CHARS, TripRequest


class StartIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    round_trip: bool = False


class PlanRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=MAX_REQUEST_CHARS,
        examples=["2 days in Lisbon with kids, we love viewpoints and old churches"],
    )
    start: StartIn | None = Field(default=None, description="Hotel or other daily start point")


class PlannedStop(BaseModel):
    place_id: int
    name: str
    category: str
    lat: float
    lon: float
    arrive: str = Field(description="HH:MM")
    leave: str = Field(description="HH:MM")
    walk_from_previous_m: int


class PlannedDay(BaseModel):
    day: int
    stops: list[PlannedStop]
    distance_m: int
    duration_min: int
    self_intersections: int
    geometry: list[tuple[float, float]] = Field(
        description="Walking path as [lon, lat] pairs (GeoJSON order)"
    )


class DroppedPlace(BaseModel):
    place_id: int
    name: str


class PlanResponse(BaseModel):
    id: int
    request_text: str
    city: str
    trip: TripRequest
    rationale: str
    days: list[PlannedDay]
    total_distance_m: int
    distance_source: str
    strategy: str
    dropped: list[DroppedPlace]
    warnings: list[str]
    timings_ms: dict[str, int]
