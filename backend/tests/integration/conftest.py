"""Integration fixtures: a throwaway PostGIS container, migrated and seeded once per run."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from sqlalchemy import select
from testcontainers.community.postgres import PostgresContainer

from app.config import get_settings
from app.db.models import Category, Place
from app.db.session import create_engine, create_sessionmaker
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[2]
POSTGIS_IMAGE = "postgis/postgis:17-3.5"

# (osm_id, city, name, category, lat, lon, wikidata)
SEED_PLACES = [
    (1, "lisbon", "Praça do Comércio", "landmark", 38.7075, -9.1364, "Q1130427"),
    (2, "lisbon", "Castelo de São Jorge", "landmark", 38.7139, -9.1335, "Q753226"),
    (3, "lisbon", "Miradouro de Santa Luzia", "viewpoint", 38.7116, -9.1301, None),
    (4, "lisbon", "Torre de Belém", "landmark", 38.6916, -9.2160, "Q213402"),
    (5, "lisbon", "Museu Calouste Gulbenkian", "museum", 38.7372, -9.1545, None),
    (6, "porto", "Museu de Serralves", "museum", 41.1597, -8.6598, None),
]


async def _seed() -> None:
    engine = create_engine()
    try:
        async with create_sessionmaker(engine)() as session, session.begin():
            category_ids = {
                slug: category_id
                for slug, category_id in await session.execute(select(Category.slug, Category.id))
            }
            session.add_all(
                Place(
                    osm_type="node",
                    osm_id=osm_id,
                    city=city,
                    name=name,
                    category_id=category_ids[category],
                    geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
                    tags={"name": name},
                    wikidata=wikidata,
                )
                for osm_id, city, name, category, lat, lon, wikidata in SEED_PLACES
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with (
        PostgresContainer(POSTGIS_IMAGE, driver="asyncpg") as postgres,
        pytest.MonkeyPatch.context() as monkeypatch,
    ):
        url = postgres.get_connection_url()
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
        asyncio.run(_seed())
        yield url
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def place_ids(database_url: str) -> dict[str, int]:
    async def load() -> dict[str, int]:
        engine = create_engine()
        try:
            async with create_sessionmaker(engine)() as session:
                rows = await session.execute(select(Place.name, Place.id))
                return {name: place_id for name, place_id in rows}
        finally:
            await engine.dispose()

    return asyncio.run(load())


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Everything under tests/integration/ needs Docker; `pytest -m "not integration"` skips it.
    for item in items:
        if "tests/integration/" in item.nodeid:
            item.add_marker(pytest.mark.integration)
