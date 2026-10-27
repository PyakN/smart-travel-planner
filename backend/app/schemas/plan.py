from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.trip import MAX_REQUEST_CHARS, TripRequest

TravelMode = Literal["walk", "transit"]
ALL_MODES: list[TravelMode] = ["walk", "transit"]
MAX_MUST_VISIT = 10


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
    must_visit: list[int] = Field(
        default_factory=list,
        max_length=MAX_MUST_VISIT,
        description="Place ids (from GET /places) that must be in the plan",
    )
    modes: list[TravelMode] = Field(
        default_factory=lambda: list(ALL_MODES),
        min_length=1,
        description="walk only: no tram/metro; transit only: ride every leg over 1 km",
    )

    @field_validator("must_visit", "modes")
    @classmethod
    def _unique[T](cls, values: list[T]) -> list[T]:
        return list(dict.fromkeys(values))


class PlannedStop(BaseModel):
    place_id: int
    name: str
    category: str
    lat: float
    lon: float
    arrive: str = Field(description="HH:MM")
    leave: str = Field(description="HH:MM")
    # How to get here from the previous stop (or the start point); null for a free start.
    travel_mode: TravelMode | None
    travel_min: int
    distance_from_previous_m: int
    must_visit: bool = False
    note: str | None = Field(default=None, description="Why this place suits the traveller")


class RouteSegment(BaseModel):
    mode: TravelMode
    geometry: list[tuple[float, float]] = Field(
        description="Path as [lon, lat] pairs (GeoJSON order); street-following when walked, "
        "a straight line for transit legs"
    )


class PlannedDay(BaseModel):
    day: int
    stops: list[PlannedStop]
    distance_m: int
    walking_m: int
    transit_legs: int
    duration_min: int
    self_intersections: int
    segments: list[RouteSegment]


class PlaceRef(BaseModel):
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
    dropped: list[PlaceRef]
    warnings: list[str]
    timings_ms: dict[str, int]
    # Defaults keep plans saved before these fields existed readable.
    modes: list[TravelMode] = Field(default_factory=lambda: list(ALL_MODES))
    must_visit: list[PlaceRef] = Field(default_factory=list)
