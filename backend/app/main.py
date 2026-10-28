import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, places, plans, trips
from app.config import get_settings
from app.db.session import create_engine, create_sessionmaker
from app.llm.base import LLMError
from app.llm.factory import create_llm_service
from app.optimizer.factory import create_distance_provider, create_transit_provider
from app.services.accounts import LoginLimiter
from app.services.weather_service import create_weather_provider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine()
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.login_limiter = LoginLimiter()
    app.state.distances = create_distance_provider(settings)
    app.state.transit = create_transit_provider(settings)
    if app.state.transit is None:
        logger.info("No HERE_API_KEY: ride times are estimates")
    app.state.weather = create_weather_provider(settings)
    if app.state.weather is None:
        logger.info("No OPENWEATHER_API_KEY: plans have no weather")
    try:
        app.state.llm = create_llm_service(settings)
    except LLMError as exc:
        # The rest of the API still works; POST /plan answers 503 until a key is set.
        logger.warning("LLM disabled: %s", exc)
        app.state.llm = None
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Smart AI Travel Planner", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(places.router)
    app.include_router(plans.router)
    app.include_router(auth.router)
    app.include_router(trips.router)
    return app


app = create_app()
