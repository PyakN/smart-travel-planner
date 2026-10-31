"""Saved trips of the logged-in user, their visited places, day edits and AI replacements.
Other users' trips answer 404; the plans themselves stay public and read-only at
GET /plans/{id} (share links)."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AI_RATE_LIMIT,
    CurrentUserDep,
    DistancesDep,
    LLMDep,
    NowDep,
    SessionDep,
    SettingsDep,
    TransitDep,
    WeatherDep,
)
from app.api.plans import planning_errors
from app.db.models import Trip, User
from app.schemas.plan import PlanResponse, ReplaceRequest
from app.schemas.saved_trip import (
    DayEdit,
    SaveTripRequest,
    TripOut,
    TripSummary,
    TripUpdate,
    TripVisitOut,
)
from app.services import saved_trips
from app.services.day_editing import edit_day
from app.services.plan_editing import replace_stops
from app.services.saved_trips import (
    NotAStopError,
    NotAVersionError,
    OutdatedVersionError,
    VisitedLeftOutError,
)
from app.services.trip_planner import get_plan

router = APIRouter(prefix="/trips", tags=["trips"])


async def _trip(session: AsyncSession, user: User, trip_id: int) -> Trip:
    trip = await saved_trips.find_trip(session, user, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trip not found")
    return trip


async def _plan(session: AsyncSession, trip: Trip) -> PlanResponse:
    plan = await get_plan(session, trip.plan_id)
    if plan is None:  # saved in a format this version cannot read
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This trip's plan can no longer be read.")
    return plan


async def _out(session: AsyncSession, trip: Trip) -> TripOut:
    return TripOut(
        id=trip.id,
        title=trip.title,
        plan=await _plan(session, trip),
        visits=await saved_trips.trip_visits(session, trip),
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


def _not_a_version(plan_id: int) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, f"Plan {plan_id} is not a version of this trip."
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"description": "Saved already: that trip"}},
)
async def save_trip(
    body: SaveTripRequest, response: Response, user: CurrentUserDep, session: SessionDep
) -> TripOut:
    """Save a plan to my trips."""
    plan = await get_plan(session, body.plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    trip, created = await saved_trips.save_trip(session, user, plan, body.title)
    if not created:
        response.status_code = status.HTTP_200_OK
    return await _out(session, trip)


@router.get("")
async def list_trips(user: CurrentUserDep, session: SessionDep) -> list[TripSummary]:
    """My trips, the most recently changed first."""
    return await saved_trips.list_trips(session, user)


@router.get("/{trip_id}")
async def read_trip(trip_id: int, user: CurrentUserDep, session: SessionDep) -> TripOut:
    """A trip with its current plan."""
    return await _out(session, await _trip(session, user, trip_id))


@router.patch("/{trip_id}")
async def update_trip(
    trip_id: int, body: TripUpdate, user: CurrentUserDep, session: SessionDep
) -> TripOut:
    """Rename a trip, or switch it to another version of its plan: a draft made from its
    current version (save), or one that version was made from (undo). A draft made from an
    outdated version, or a version that leaves out a visited place, is refused (409)."""
    trip = await _trip(session, user, trip_id)
    plan: PlanResponse | None = None
    if body.plan_id is not None:
        plan = await get_plan(session, body.plan_id)
        if plan is None:
            raise _not_a_version(body.plan_id)
    try:
        await saved_trips.update_trip(session, trip, title=body.title, plan=plan)
    except NotAVersionError as exc:
        raise _not_a_version(exc.args[0]) from exc
    except OutdatedVersionError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The trip changed after this draft was made from it. Make the change again.",
        ) from exc
    except VisitedLeftOutError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"That version leaves out places you visited: {exc}."
        ) from exc
    return await _out(session, trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: int, user: CurrentUserDep, session: SessionDep) -> None:
    """Delete a trip; its plans stay readable by their links."""
    await saved_trips.delete_trip(session, await _trip(session, user, trip_id))


@router.put("/{trip_id}/visits/{place_id}")
async def mark_visited(
    trip_id: int, place_id: int, user: CurrentUserDep, session: SessionDep
) -> TripVisitOut:
    """Tick a stop of the trip visited (again: it keeps its first time)."""
    trip = await _trip(session, user, trip_id)
    try:
        return await saved_trips.mark_visited(session, trip, await _plan(session, trip), place_id)
    except NotAStopError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Place {place_id} is not a stop of this trip."
        ) from exc


@router.delete("/{trip_id}/visits/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_visited(
    trip_id: int, place_id: int, user: CurrentUserDep, session: SessionDep
) -> None:
    """Untick a visited stop."""
    await saved_trips.unmark_visited(session, await _trip(session, user, trip_id), place_id)


@router.post("/{trip_id}/edit", status_code=status.HTTP_201_CREATED)
async def edit_trip_day(
    trip_id: int,
    body: DayEdit,
    user: CurrentUserDep,
    session: SessionDep,
    distances: DistancesDep,
    transit: TransitDep,
    weather: WeatherDep,
    settings: SettingsDep,
    now: NowDep,
) -> PlanResponse:
    """Change one day of a trip: take stops out, add places, choose the next stop, or plan
    the rest of the day from where you are (no AI). Visited stops stay first. Answers with a
    draft: a new version of the plan (`parent_id`: the trip's current one) that the trip
    uses once it is saved (PATCH with its `plan_id`). `edit.dropped` lists the planned
    stops it leaves out, and why."""
    trip = await _trip(session, user, trip_id)
    plan = await _plan(session, trip)
    visits = await saved_trips.trip_visits(session, trip)
    async with planning_errors(settings.plan_timeout_s):
        return await edit_day(
            session=session,
            distances=distances,
            plan=plan,
            visited={v.place_id for v in visits},
            edit=body,
            now=now,
            transit=transit,
            weather=weather,
        )


@router.post(
    "/{trip_id}/replace", status_code=status.HTTP_201_CREATED, dependencies=[AI_RATE_LIMIT]
)
async def replace_trip_stops(
    trip_id: int,
    body: ReplaceRequest,
    user: CurrentUserDep,
    session: SessionDep,
    llm: LLMDep,
    distances: DistancesDep,
    transit: TransitDep,
    weather: WeatherDep,
    settings: SettingsDep,
) -> PlanResponse:
    """Replace stops of one day of a trip with places the AI picks, as POST
    /plans/{id}/replace does for its current version. Visited stops cannot be replaced: they
    stay first, as they were, and the rest of the day follows them. Answers with a draft,
    like an edit."""
    trip = await _trip(session, user, trip_id)
    plan = await _plan(session, trip)
    visits = await saved_trips.trip_visits(session, trip)
    async with planning_errors(settings.plan_timeout_s):
        draft = await replace_stops(
            session=session,
            llm=llm,
            distances=distances,
            plan_id=plan.id,
            day=body.day,
            place_ids=body.place_ids,
            transit=transit,
            weather=weather,
            visited={v.place_id for v in visits},
        )
    if draft is None:  # the plan was read just now
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This trip's plan can no longer be read.")
    return draft
