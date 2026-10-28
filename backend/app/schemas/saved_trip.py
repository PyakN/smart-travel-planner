"""Saved trips (`/trips`). Not to be confused with app.schemas.trip, the request the LLM
parses."""

import datetime as dt
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

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
