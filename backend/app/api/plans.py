import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, status

from app.api.deps import (
    AI_RATE_LIMIT,
    DistancesDep,
    LLMDep,
    SessionDep,
    SettingsDep,
    TransitDep,
    WeatherDep,
)
from app.schemas.plan import PlanRequest, PlanResponse, ReplaceRequest
from app.services.day_hours import DailyHours
from app.services.place_selection import PlanningError
from app.services.plan_editing import replace_stops
from app.services.trip_planner import get_plan, plan_trip

router = APIRouter(tags=["plans"])


@asynccontextmanager
async def planning_errors(timeout_s: float) -> AsyncIterator[None]:
    """Run planning work under a deadline and turn its failures into clear HTTP errors. LLM
    failures are none: plans are made without it then (app.services.ai_fallback)."""
    try:
        async with asyncio.timeout(timeout_s):
            yield
    except PlanningError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "Planning took too long. Try a shorter trip."
        ) from exc


@router.post("/plan", status_code=status.HTTP_201_CREATED, dependencies=[AI_RATE_LIMIT])
async def create_plan(
    body: PlanRequest,
    session: SessionDep,
    llm: LLMDep,
    distances: DistancesDep,
    transit: TransitDep,
    weather: WeatherDep,
    settings: SettingsDep,
) -> PlanResponse:
    async with planning_errors(settings.plan_timeout_s):
        return await plan_trip(
            session=session,
            llm=llm,
            distances=distances,
            text=body.text,
            start=body.start,
            default_city=settings.default_city,
            must_visit=body.must_visit,
            modes=body.modes,
            transit=transit,
            weather=weather,
            start_date=body.start_date,
            weather_aware=body.weather_aware,
            hours=DailyHours(
                body.day_start,
                body.day_end,
                body.first_day_start,
                tuple((h.start, h.end) for h in body.day_hours),
            ),
            day_count=body.day_count,
            chosen_city=body.city,
        )


@router.post(
    "/plans/{plan_id}/replace",
    status_code=status.HTTP_201_CREATED,
    dependencies=[AI_RATE_LIMIT],
)
async def replace_plan_stops(
    plan_id: int,
    body: ReplaceRequest,
    session: SessionDep,
    llm: LLMDep,
    distances: DistancesDep,
    transit: TransitDep,
    weather: WeatherDep,
    settings: SettingsDep,
) -> PlanResponse:
    """Replace stops of one day; answers with a new plan version (`parent_id` = this plan)."""
    async with planning_errors(settings.plan_timeout_s):
        plan = await replace_stops(
            session=session,
            llm=llm,
            distances=distances,
            plan_id=plan_id,
            day=body.day,
            place_ids=body.place_ids,
            transit=transit,
            weather=weather,
        )
        if plan is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
        return plan


@router.get("/plans/{plan_id}")
async def read_plan(plan_id: int, session: SessionDep) -> PlanResponse:
    plan = await get_plan(session, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    return plan
