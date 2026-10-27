from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.trip import MAX_REQUEST_CHARS, TripRequest

TravelMode = Literal["walk", "transit"]
ALL_MODES: list[TravelMode] = ["walk", "transit"]
TransitVehicle = Literal[
    "metro", "tram", "bus", "train", "ferry", "funicular", "cable_car", "other"
]
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


class StopPhoto(BaseModel):
    url: str = Field(description="Thumbnail, about 500 px wide")
    page_url: str | None = Field(description="Wikimedia Commons file page: author and licence")
    credit: str | None = Field(description="Author and licence, e.g. 'Jane Doe, CC BY-SA 4.0'")


class Attribution(BaseModel):
    text: str = Field(description="Data credit the transit operator requires with its routes")
    url: str | None


class TransitRide(BaseModel):
    vehicle: TransitVehicle
    line: str = Field(description="Line name, e.g. '28E', 'Verde' (metro), 'Linha de Cascais'")
    headsign: str | None = Field(description="Where the vehicle is going")
    color: str | None = Field(description="The line's own colour, '#RRGGBB'")
    board: str | None = Field(description="Stop to get on at")
    alight: str | None = Field(description="Stop to get off at")
    stops: int = Field(description="Number of stops ridden")
    minutes: int
    attributions: list[Attribution] = Field(default_factory=list)


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
    rides: list[TransitRide] = Field(
        default_factory=list,
        description="The rides of a transit leg, in order; empty for walks and estimated rides",
    )
    must_visit: bool = False
    note: str | None = Field(default=None, description="Why this place suits the traveller")
    description: str | None = None
    photo: StopPhoto | None = None
    opening_hours: str | None = Field(default=None, description="OpenStreetMap syntax")
    website: str | None = None


class RouteSegment(BaseModel):
    mode: TravelMode
    geometry: list[tuple[float, float]] = Field(
        description="Path as [lon, lat] pairs (GeoJSON order): street-following when walked, "
        "along the line when ridden, a straight line for an estimated ride"
    )
    ride: TransitRide | None = Field(default=None, description="The ride of a transit segment")


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


class ReplaceRequest(BaseModel):
    day: int = Field(ge=1)
    place_ids: list[int] = Field(
        min_length=1, max_length=20, description="Stops of that day to replace"
    )


class Adjustment(BaseModel):
    """A change to a stop the traveller did not tick, made to keep the day full and varied."""

    removed: PlaceRef | None
    added: PlaceRef | None
    reason: str


class PlanEdit(BaseModel):
    day: int
    replaced: list[PlaceRef] = Field(description="Stops the traveller asked to replace")
    added: list[PlaceRef] = Field(description="Their replacements")
    adjustments: list[Adjustment] = Field(description="Last-resort changes to other stops")


class PlanResponse(BaseModel):
    id: int
    request_text: str
    city: str
    trip: TripRequest
    rationale: str
    days: list[PlannedDay]
    total_distance_m: int
    distance_source: str
    # "here" (real timetables), "estimate", "mixed"; None when nothing is ridden.
    transit_source: str | None = None
    strategy: str
    dropped: list[PlaceRef]
    warnings: list[str]
    timings_ms: dict[str, int]
    # Defaults keep plans saved before these fields existed readable.
    modes: list[TravelMode] = Field(default_factory=lambda: list(ALL_MODES))
    must_visit: list[PlaceRef] = Field(default_factory=list)
    start: StartIn | None = None
    # Set on versions made by replacing stops: the plan this one was made from, and how.
    parent_id: int | None = None
    edit: PlanEdit | None = None
