"""Saved trips: a user's plans, by their current version.

A trip points at one version of a plan. Editing a plan saves a new version that names the
one it was made from (`parent_id` in its params). Versions that go back to the same first
plan, edit after edit, are versions of the same trip, and a trip can switch between them:
to a draft made from it (save) or to an earlier version (undo).
"""

from datetime import date

from sqlalchemy import BigInteger, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Route, Trip, User
from app.ingest.cities import CITIES
from app.schemas.plan import PlanResponse
from app.schemas.saved_trip import TripSummary


class NotAVersionError(Exception):
    """The plan is not a version of the trip's plan."""


def default_title(plan: PlanResponse) -> str:
    city = CITIES.get(plan.city)
    days = len(plan.days)
    return f"{days} {'day' if days == 1 else 'days'} in {city.name if city else plan.city.title()}"


async def first_version(session: AsyncSession, plan_id: int) -> int | None:
    """The plan `plan_id` was made from, edit after edit (itself if it is not an edit);
    None if there is no such plan."""
    newer = aliased(Route)
    chain = (
        select(Route.id, Route.params["parent_id"].astext.cast(BigInteger).label("parent"))
        .where(Route.id == plan_id)
        .cte("chain", recursive=True)
    )
    chain = chain.union_all(
        select(newer.id, newer.params["parent_id"].astext.cast(BigInteger)).join(
            chain, newer.id == chain.c.parent
        )
    )
    first: int | None = await session.scalar(select(chain.c.id).where(chain.c.parent.is_(None)))
    return first


async def find_trip(session: AsyncSession, user: User, trip_id: int) -> Trip | None:
    """One of the user's trips: other users' trips are not found."""
    trip: Trip | None = await session.scalar(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id)
    )
    return trip


async def save_trip(
    session: AsyncSession, user: User, plan: PlanResponse, title: str | None
) -> tuple[Trip, bool]:
    """Save `plan` as a trip; True if new. A plan the user saved already gives that trip."""
    saved = await session.scalar(
        select(Trip).where(Trip.user_id == user.id, Trip.plan_id == plan.id).order_by(Trip.id)
    )
    if saved is not None:
        return saved, False
    trip = Trip(user_id=user.id, title=title or default_title(plan), plan_id=plan.id)
    session.add(trip)
    await session.commit()
    return trip, True


async def list_trips(session: AsyncSession, user: User) -> list[TripSummary]:
    """The user's trips, the most recently changed first."""
    rows = await session.execute(
        select(
            Trip,
            Route.city,
            Route.request_text,
            Route.result["start_date"].astext.label("start_date"),
            func.jsonb_array_length(Route.result["days"]).label("days"),
        )
        .join(Route, Route.id == Trip.plan_id)
        .where(Trip.user_id == user.id)
        .order_by(Trip.updated_at.desc(), Trip.id.desc())
    )
    return [
        TripSummary(
            id=row.Trip.id,
            title=row.Trip.title,
            plan_id=row.Trip.plan_id,
            city=row.city,
            request_text=row.request_text,
            days=row.days,
            start_date=date.fromisoformat(row.start_date) if row.start_date else None,
            created_at=row.Trip.created_at,
            updated_at=row.Trip.updated_at,
        )
        for row in rows
    ]


async def update_trip(
    session: AsyncSession, trip: Trip, *, title: str | None, plan: PlanResponse | None
) -> None:
    """Rename the trip and/or switch it to another version of its plan."""
    if plan is not None and plan.id != trip.plan_id:
        if await first_version(session, plan.id) != await first_version(session, trip.plan_id):
            raise NotAVersionError(plan.id)
        trip.plan_id = plan.id
    if title is not None:
        trip.title = title
    await session.commit()
    await session.refresh(trip)  # updated_at is set by the database


async def delete_trip(session: AsyncSession, trip: Trip) -> None:
    """The trip goes; its plans stay (share links)."""
    await session.delete(trip)
    await session.commit()
