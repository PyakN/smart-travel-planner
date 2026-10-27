from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.llm.service import LLMService
from app.optimizer.distance import DistanceProvider
from app.optimizer.transit import TransitProvider


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


def get_llm(request: Request) -> LLMService:
    llm: LLMService | None = request.app.state.llm
    if llm is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The AI planner is not configured."
        )
    return llm


def get_distances(request: Request) -> DistanceProvider:
    distances: DistanceProvider = request.app.state.distances
    return distances


def get_transit(request: Request) -> TransitProvider | None:
    """Real public transport routes; None means estimated ride times."""
    transit: TransitProvider | None = request.app.state.transit
    return transit


SessionDep = Annotated[AsyncSession, Depends(get_session)]
LLMDep = Annotated[LLMService, Depends(get_llm)]
DistancesDep = Annotated[DistanceProvider, Depends(get_distances)]
TransitDep = Annotated[TransitProvider | None, Depends(get_transit)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
