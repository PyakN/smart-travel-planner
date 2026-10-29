"""Integration fixtures: a throwaway PostGIS container, migrated and seeded once per run."""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from app.api.deps import get_distances, get_llm, get_transit, get_weather
from app.config import get_settings
from app.db.models import Category, Place
from app.db.session import create_engine, create_sessionmaker
from app.llm.service import LLMService
from app.main import create_app
from app.optimizer.distance import HaversineProvider
from tests.fakes import FakeProvider

BACKEND_DIR = Path(__file__).resolve().parents[2]
POSTGIS_IMAGE = "postgis/postgis:17-3.5"

# (osm_id, city, name, category, lat, lon, wikidata, extra tags)
SEED_PLACES: list[tuple[int, str, str, str, float, float, str | None, dict[str, str]]] = [
    (1, "lisbon", "Praça do Comércio", "landmark", 38.7075, -9.1364, "Q1130427", {}),
    (2, "lisbon", "Castelo de São Jorge", "landmark", 38.7139, -9.1335, "Q753226", {}),
    (3, "lisbon", "Miradouro de Santa Luzia", "viewpoint", 38.7116, -9.1301, None, {}),
    (
        4,
        "lisbon",
        "Torre de Belém",
        "landmark",
        38.6916,
        -9.2160,
        "Q213402",
        {"name:en": "Belém Tower", "wikipedia": "pt:Torre de Belém"},
    ),
    (5, "lisbon", "Museu Calouste Gulbenkian", "museum", 38.7372, -9.1545, None, {}),
    (6, "porto", "Museu de Serralves", "museum", 41.1597, -8.6598, None, {}),
    # A compact fictional town with plenty of places, for tests that need spare candidates
    # (replacing stops). Its city is registered in CITIES only by the tests that use it.
    (101, "testville", "Testville Cathedral", "religious", 45.0000, 7.0000, "Q900001", {}),
    (102, "testville", "Old Town Square", "landmark", 45.0010, 7.0020, "Q900002", {}),
    (103, "testville", "Clock Tower", "landmark", 45.0020, 7.0010, None, {}),
    (104, "testville", "City Museum", "museum", 45.0030, 7.0030, "Q900004", {}),
    (
        105,
        "testville",
        "Museum of Toys",
        "museum",
        45.0040,
        7.0000,
        None,
        {"opening_hours": "Tu-Su 10:00-18:00"},
    ),
    (106, "testville", "Hilltop Viewpoint", "viewpoint", 45.0050, 7.0040, None, {}),
    (107, "testville", "River Park", "park", 45.0020, 7.0060, None, {}),
    (108, "testville", "Saint Anne Church", "religious", 45.0060, 7.0020, None, {}),
    (109, "testville", "Saint Paul Church", "religious", 45.0070, 7.0010, None, {}),
    (110, "testville", "Fish Market", "market", 45.0010, 7.0050, None, {}),
    (111, "testville", "Modern Art Gallery", "gallery", 45.0030, 7.0070, None, {}),
    (112, "testville", "Harbour Theatre", "culture", 45.0000, 7.0080, None, {}),
    (113, "testville", "Far Fort", "landmark", 45.0800, 7.0900, "Q900013", {}),
    # Open at night only: plans offer them for evenings, from 20:00.
    (114, "testville", "Harbour Bar", "nightlife", 45.0005, 7.0075, None, {"amenity": "bar"}),
    (115, "testville", "Old Town Fado", "restaurant", 45.0015, 7.0035, None, {}),
    # Sights open at night too: a lit square, and a market hall open late.
    (116, "testville", "Lantern Square", "landmark", 45.0012, 7.0045, None, {"place": "square"}),
    (
        117,
        "testville",
        "Night Market",
        "market",
        45.0025,
        7.0050,
        None,
        {"building": "yes", "opening_hours": "Mo-Su 10:00-23:00"},
    ),
]
# Stop-card details (normally from OSM tags and app.ingest.enrich), by place name.
SEED_DETAILS: dict[str, dict[str, str]] = {
    "Castelo de São Jorge": {
        "description": "São Jorge Castle is a historic castle in Lisbon.",
        "opening_hours": "Mo-Su 09:00-21:00",
        "website": "https://castelodesaojorge.pt",
        "image_url": "https://thumb.wikimedia.org/x/500px-Castelo.jpg",
        "image_page_url": "https://commons.wikimedia.org/wiki/File:Castelo.jpg",
        "image_credit": "Jane, CC BY-SA 4.0",
    }
}


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
                    tags={"name": name, **extra_tags},
                    wikidata=wikidata,
                    **SEED_DETAILS.get(name, {}),
                )
                for osm_id, city, name, category, lat, lon, wikidata, extra_tags in SEED_PLACES
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
        monkeypatch.setenv("TRANSIT_PROVIDER", "estimate")  # tests that ride use a fake
        monkeypatch.setenv("OPENWEATHER_API_KEY", "")  # tests with weather use a fake
        get_settings.cache_clear()
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
        asyncio.run(_seed())
        yield url
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@pytest.fixture
def db_session(database_url: str) -> SessionFactory:
    """Factory for sessions bound to the test database; use inside asyncio.run()."""

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[AsyncSession]:
        engine = create_engine()
        try:
            async with create_sessionmaker(engine)() as session:
                yield session
        finally:
            await engine.dispose()

    return session_scope


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


def use_llm(client: TestClient, provider: FakeProvider, **service_kwargs: Any) -> None:
    service = LLMService(provider, model="fake", max_retries=0, **service_kwargs)
    client.app.dependency_overrides[get_llm] = lambda: service  # type: ignore[attr-defined]


@pytest.fixture
def llm(client: TestClient) -> Iterator[FakeProvider]:
    """Scripted LLM, straight-line distances and estimated ride times for API tests."""
    provider = FakeProvider()
    use_llm(client, provider)
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_distances] = HaversineProvider
    overrides[get_transit] = lambda: None
    overrides[get_weather] = lambda: None
    yield provider
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def visitor(client: TestClient) -> Iterator[TestClient]:
    """The API client, logged out before and after the test."""
    client.cookies.clear()
    yield client
    client.cookies.clear()


PASSWORD = "correct horse"


def sign_up(client: TestClient, name: str = "Ana") -> dict[str, Any]:
    """A new account with a unique email, logged in on `client`; returns the user."""
    email = f"{name.lower()}-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/auth/signup", json={"email": email, "password": PASSWORD, "display_name": name}
    )
    assert response.status_code == 201, response.text
    user: dict[str, Any] = response.json()
    return user


def session_token(client: TestClient) -> str:
    return client.cookies["session"]


def use_session(client: TestClient, token: str) -> None:
    """Act as the user `token` belongs to."""
    client.cookies.clear()
    client.cookies.set("session", token)
