from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def create_engine() -> AsyncEngine:
    # A hosted database may close idle connections (Neon closes them all when it suspends
    # after a few idle minutes): each one is checked as it leaves the pool, instead of
    # failing the request it was taken for.
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
