from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep
from app.llm.service import LLMService

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    llm: Literal["ok", "unavailable", "not_configured"] = Field(
        description="unavailable: it failed repeatedly and is not called for a while"
    )


@router.get("/health")
async def health(request: Request, session: SessionDep) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    llm: LLMService | None = request.app.state.llm
    return HealthOut(
        status="ok",
        database="ok",
        llm="not_configured" if llm is None else "unavailable" if llm.circuit.is_open else "ok",
    )
