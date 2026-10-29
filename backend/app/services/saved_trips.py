"""Saved trips: a user's plans, by their current version.

A trip points at one version of a plan. Editing a plan saves a new version that names the
one it was made from (`parent_id` in its params). Versions that go back to the same first
plan, edit after edit, are versions of the same trip, and a trip can switch between them:
to a draft made from it (save) or to an earlier version (undo).

Visited places live on the trip, so there is one record of them whatever the version; a
version that leaves a visited place out is refused.
"""

from datetime import date

from sqlalchemy import BigInteger, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Place, Route, Trip, TripVisit, User
from app.ingest.cities import CITIES
from app.schemas.plan import PlanResponse
from app.schemas.saved_trip import TripSummary, TripVisitOut


class NotAVersionError(Exception):
    """The plan is not a version of the trip's plan."""


class NotAStopError(Exception):
    """The place is not a stop of the trip's current plan."""


class VisitedLeftOutError(Exception):
    """The version leaves out places the traveller has visited."""

    def __init__(self, visits: list[TripVisitOut]) -> None:
        super().__init__(", ".join(v.name for v in visits))
        self.visits = visits


def stop_ids(plan: PlanResponse) -> set[int]:
    return {stop.place_id for day in plan.days for stop in day.stops}


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
    # One save at a time per user: two saves of a plan at once still make one trip.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
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


async def trip_visits(session: AsyncSession, trip: Trip) -> list[TripVisitOut]:
    """The trip's visited places, in visiting order."""
    rows = await session.execute(
        select(TripVisit.place_id, Place.name, TripVisit.visited_at)
        .join(Place, Place.id == TripVisit.place_id)
        .where(TripVisit.trip_id == trip.id)
        .order_by(TripVisit.visited_at, TripVisit.place_id)
    )
    return [
        TripVisitOut(place_id=row.place_id, name=row.name, visited_at=row.visited_at)
        for row in rows
    ]


async def _touch(session: AsyncSession, trip: Trip) -> None:
    """A change to the trip: it moves to the top of the list."""
    await session.execute(update(Trip).where(Trip.id == trip.id).values(updated_at=func.now()))


async def mark_visited(
    session: AsyncSession, trip: Trip, plan: PlanResponse, place_id: int
) -> TripVisitOut:
    """Tick a stop of the trip's current plan visited; ticking it again keeps the first time."""
    if place_id not in stop_ids(plan):
        raise NotAStopError(place_id)
    await session.execute(
        insert(TripVisit).values(trip_id=trip.id, place_id=place_id).on_conflict_do_nothing()
    )
    await _touch(session, trip)
    await session.commit()
    return next(v for v in await trip_visits(session, trip) if v.place_id == place_id)


async def unmark_visited(session: AsyncSession, trip: Trip, place_id: int) -> None:
    await session.execute(
        delete(TripVisit).where(TripVisit.trip_id == trip.id, TripVisit.place_id == place_id)
    )
    await _touch(session, trip)
    await session.commit()


async def update_trip(
    session: AsyncSession, trip: Trip, *, title: str | None, plan: PlanResponse | None
) -> None:
    """Rename the trip and/or switch it to another version of its plan, which must keep
    every visited place."""
    if plan is not None and plan.id != trip.plan_id:
        if await first_version(session, plan.id) != await first_version(session, trip.plan_id):
            raise NotAVersionError(plan.id)
        stops = stop_ids(plan)
        if left_out := [v for v in await trip_visits(session, trip) if v.place_id not in stops]:
            raise VisitedLeftOutError(left_out)
        trip.plan_id = plan.id
    if title is not None:
        trip.title = title
    await session.commit()
    await session.refresh(trip)  # updated_at is set by the database


async def delete_trip(session: AsyncSession, trip: Trip) -> None:
    """The trip goes; its plans stay (share links)."""
    await session.delete(trip)
    await session.commit()
