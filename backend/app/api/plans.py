import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DistancesDep, LLMDep, SessionDep, SettingsDep
from app.llm.base import LLMBudgetExceededError, LLMError, LLMUnavailableError
from app.schemas.plan import PlanRequest, PlanResponse
from app.services.place_selection import PlanningError
from app.services.trip_planner import get_plan, plan_trip

logger = logging.getLogger(__name__)
router = APIRouter(tags=["plans"])


@router.post("/plan", status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: PlanRequest,
    session: SessionDep,
    llm: LLMDep,
    distances: DistancesDep,
    settings: SettingsDep,
) -> PlanResponse:
    try:
        async with asyncio.timeout(settings.plan_timeout_s):
            return await plan_trip(
                session=session,
                llm=llm,
                distances=distances,
                text=body.text,
                start=body.start,
                default_city=settings.default_city,
            )
    except PlanningError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except LLMBudgetExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Planning capacity for today is used up."
        ) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI planner is temporarily unavailable. Try again shortly.",
        ) from exc
    except LLMError as exc:
        logger.exception("LLM rejected the planning request")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI planner failed.") from exc
    except TimeoutError as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "Planning took too long. Try a shorter trip."
        ) from exc


@router.get("/plans/{plan_id}")
async def read_plan(plan_id: int, session: SessionDep) -> PlanResponse:
    plan = await get_plan(session, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    return plan
