import datetime as dt  # PlannedDay has a field named `date`
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.catalog import VisitHours
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
        description="Plan with the forecast of the days' hours: keep outdoor stops out of rain, "
        "snow and fog, swap some for indoor places when it leaves too few dry hours, and show "
        "it. Without it, no forecast is fetched",
    )
    day_start: dt.time = Field(
        default=dt.time(9, 30), description="When each day starts, in the city's local time"
    )
    day_end: dt.time = Field(
        default=dt.time(21, 30),
        description="When each day ends; earlier than day_start: the next morning (16:00 to "
        "03:00). After 20:00 the plan has a few places open at night (lit squares, sights open "
        "late); the rest of the evening is free",
    )
    first_day_start: dt.time | None = Field(
        default=None,
        description="When the first day starts, if not at day_start (e.g. now, for a trip that "
        "starts today). A trip that starts today never starts before the current time",
    )

    @field_validator("must_visit", "modes")
    @classmethod
    def _unique[T](cls, values: list[T]) -> list[T]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def _day_has_hours(self) -> Self:
        if self.day_start == self.day_end:
            raise ValueError("day_end must differ from day_start")
        return self


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


class Departure(BaseModel):
    """Where and when the way to a stop starts, when not at the stop before it."""

    lat: float
    lon: float
    time: str = Field(description="HH:MM")


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
    hours: VisitHours = Field(
        default="any",
        description="When it can be visited: day (until 20:00), daylight, night (from 20:00), any",
    )
    wait_min: int = Field(default=0, description="Free time before setting off: it opens later")
    departure: Departure | None = Field(
        default=None,
        description="Where the way here starts when not at the stop before: the traveller's "
        "location, on a day re-planned from it",
    )


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
    # The day's hours, HH:MM (`end` may be the next morning), and its daylight; None on
    # plans saved before days had their own hours.
    start: str | None = None
    end: str | None = None
    sunrise: str | None = None
    sunset: str | None = None


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


class DroppedStop(PlaceRef):
    reason: str = Field(description="e.g. 'The day would end at 23:10 instead of 21:30.'")


class PlanEdit(BaseModel):
    """How a version was made from the one before: AI replacements ("replace") or a day edit
    of a saved trip ("edit": stops removed, places added, a next stop, a new start)."""

    day: int
    kind: Literal["replace", "edit"] = "replace"
    replaced: list[PlaceRef] = Field(
        default_factory=list, description="Stops the traveller asked to replace"
    )
    removed: list[PlaceRef] = Field(
        default_factory=list, description="Stops the traveller took out"
    )
    added: list[PlaceRef] = Field(description="Replacements, or places the traveller added")
    next: PlaceRef | None = Field(default=None, description="The stop the traveller visits next")
    adjustments: list[Adjustment] = Field(
        default_factory=list, description="Last-resort changes to other stops"
    )
    dropped: list[DroppedStop] = Field(
        default_factory=list, description="Planned stops the change leaves out, and why"
    )
    warnings: list[str] = Field(default_factory=list)


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
    # Set on versions made by replacing stops or editing a day: the plan this one was made
    # from, and how.
    parent_id: int | None = None
    edit: PlanEdit | None = None
    start_date: dt.date | None = None
    weather_aware: bool = False
    # Outdoor picks the forecast left no room for, and the indoor places that replaced them.
    weather_swaps: list[Adjustment] = Field(default_factory=list)
    # Picks the days' hours had no room for (dark or closed then), and what replaced them.
    hours_swaps: list[Adjustment] = Field(default_factory=list)
    # The hours asked for, HH:MM (see PlanRequest).
    day_start: str = "09:30"
    day_end: str = "21:30"
    first_day_start: str | None = None
