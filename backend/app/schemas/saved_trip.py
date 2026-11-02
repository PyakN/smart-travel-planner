"""Saved trips (`/trips`). Not to be confused with app.schemas.trip, the request the LLM
parses."""

import datetime as dt
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from app.schemas.plan import PlanResponse


def _not_blank(title: str) -> str:
    if not title.strip():
        raise ValueError("the title cannot be blank")
    return title.strip()


Title = Annotated[str, Field(max_length=100), AfterValidator(_not_blank)]


class SaveTripRequest(BaseModel):
    plan_id: int = Field(description="The plan to save (from POST /plan or GET /plans/{id})")
    title: Title | None = Field(default=None, description="Default: '2 days in Lisbon'")


class TripUpdate(BaseModel):
    title: Title | None = None
    plan_id: int | None = Field(
        default=None,
        description="Another version of this trip's plan to use from now on: a draft made "
        "from it (save), or an earlier version (undo)",
    )

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if self.title is None and self.plan_id is None:
            raise ValueError("give a title or a plan_id")
        return self


MAX_EDIT_PLACES = 20
# Stops in a day's order: more than any day holds.
MAX_ORDER = 50


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DayEdit(BaseModel):
    """A change to one day of a trip. Only the optimizer runs: no AI."""

    day: int = Field(ge=1)
    remove: list[int] = Field(
        default_factory=list, max_length=MAX_EDIT_PLACES, description="Stops of the day to take out"
    )
    add: list[int] = Field(
        default_factory=list,
        max_length=MAX_EDIT_PLACES,
        description="Places to add (ids from GET /places)",
    )
    next: int | None = Field(
        default=None, description="Visit this place next: a stop of the day, or a place to add"
    )
    after: int | None = Field(
        default=None,
        description="A stop of the day to visit `next` right after: the stops planned up to "
        "it keep their order. By default `next` comes first, after the visited stops",
    )
    start: Location | None = Field(
        default=None,
        description="Where the traveller is: the rest of the day is planned from there, from "
        "now on if the day is today",
    )
    stay_min: int | None = Field(
        default=None,
        ge=5,
        le=8 * 60,
        description="Minutes to stay at the added places and the next stop; by default, the "
        "usual visit of their kind",
    )
    order: list[int] | None = Field(
        default=None,
        max_length=MAX_ORDER,
        description="Every stop of the day that is not visited (nor removed), and the places "
        "added, in the order to visit them, after the visited stops: the day keeps this order "
        "(nothing is reordered or dropped; the draft warns when it runs late)",
    )

    @field_validator("remove", "add")
    @classmethod
    def _unique(cls, values: list[int]) -> list[int]:
        return list(dict.fromkeys(values))

    @field_validator("order")
    @classmethod
    def _once_each(cls, order: list[int] | None) -> list[int] | None:
        if order is not None and len(set(order)) < len(order):
            raise ValueError("each stop comes once in the order")
        return order

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not (
            self.remove or self.add or self.next is not None or self.start or self.order is not None
        ):
            raise ValueError(
                "give stops to remove, places to add, a next stop, a start or an order"
            )
        if set(self.remove) & set(self.add):
            raise ValueError("a place cannot be removed and added at once")
        if self.next in self.remove:
            raise ValueError("the next stop cannot be removed")
        if self.after is not None and self.next is None:
            raise ValueError("after is for the next stop")
        if self.after is not None and self.after == self.next:
            raise ValueError("the next stop cannot follow itself")
        if self.after in self.remove:
            raise ValueError("the stop the next one follows cannot be removed")
        if self.stay_min is not None and not (self.add or self.next is not None):
            raise ValueError("stay_min is for added places and the next stop")
        if self.order is not None and self.next is not None:
            raise ValueError("an order says which stop is next: give one or the other")
        if self.order is not None and set(self.order) & set(self.remove):
            raise ValueError("a removed stop cannot be in the order")
        return self


class TripSummary(BaseModel):
    id: int
    title: str
    plan_id: int = Field(description="The current version of the plan")
    city: str
    request_text: str
    days: int
    start_date: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime


class TripVisitOut(BaseModel):
    place_id: int
    name: str
    visited_at: dt.datetime


class TripOut(BaseModel):
    id: int
    title: str
    plan: PlanResponse = Field(description="The current version of the plan")
    visits: list[TripVisitOut] = Field(description="Stops visited so far, in visiting order")
    created_at: dt.datetime
    updated_at: dt.datetime
