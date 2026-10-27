import datetime as dt  # PlannedDay has a field named `date`
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.trip import MAX_REQUEST_CHARS, TripRequest

TravelMode = Literal["walk", "transit"]
ALL_MODES: list[TravelMode] = ["walk", "transit"]
TransitVehicle = Literal[
    "metro", "tram", "bus", "train", "ferry", "funicular", "cable_car", "other"
]
WeatherCondition = Literal["clear", "clouds", "fog", "drizzle", "rain", "snow", "thunderstorm"]
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
    start_date: dt.date | None = Field(
        default=None, description="First day of the trip (the city's local date); tomorrow if unset"
    )
    weather_aware: bool = Field(
        default=False,
        description="Keep outdoor stops out of rain, snow, fog and darkness, and swap some for "
        "indoor places when the forecast leaves too few dry daylight hours",
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


class ForecastSlot(BaseModel):
    time: str = Field(description="HH:MM: the forecast holds for the 3 hours around it")
    temp_c: int
    condition: WeatherCondition
    description: str = Field(description="e.g. 'light rain'")
    icon: str = Field(description="OpenWeatherMap icon code, e.g. '10d' ('n' at night)")
    pop: int = Field(description="Chance of rain or snow, %")


class StopForecast(ForecastSlot):
    """The forecast at the stop's arrival."""

    warning: str | None = Field(
        default=None, description="Outdoor stops only: rain, fog or darkness spoils the visit"
    )


class DayForecast(BaseModel):
    """The weather of a day's sightseeing hours, headed by its worst bad spell (if any)."""

    condition: WeatherCondition
    description: str
    icon: str
    temp_min_c: int
    temp_max_c: int
    pop: int = Field(description="Highest chance of rain or snow, %")
    sunrise: str = Field(description="HH:MM")
    sunset: str = Field(description="HH:MM")
    slots: list[ForecastSlot]


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
    outdoor: bool = Field(default=False, description="Visited in the open air")
    weather: StopForecast | None = None


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
    date: dt.date | None = None
    weather: DayForecast | None = Field(default=None, description="None past the forecast")


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
    start_date: dt.date | None = None
    weather_aware: bool = False
    # Outdoor picks the forecast left no room for, and the indoor places that replaced them.
    weather_swaps: list[Adjustment] = Field(default_factory=list)
