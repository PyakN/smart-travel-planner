"""The API for the end-to-end tests (frontend/e2e), on a database of its own.

    python -m tests.e2e.server [--port 8100]

Creates the database `<name>_e2e` next to DATABASE_URL's (or empties it), migrates it,
seeds a few Lisbon sights and serves the real app on it, with the scripted LLM of
tests.e2e.llm, straight-line distances, estimated rides, no weather and no rate limits.
"""

import argparse
import asyncio
import os
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from geoalchemy2 import WKTElement
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.deps import get_llm
from app.config import get_settings
from app.db.models import Category, Place
from app.db.session import create_engine, create_sessionmaker
from app.main import create_app
from tests.e2e.llm import e2e_llm

BACKEND_DIR = Path(__file__).resolve().parents[2]

# (name, category, lat, lon, Wikipedia languages, extra columns); Wikidata ids are made up.
PLACES: list[tuple[str, str, float, float, int, dict[str, str]]] = [
    (
        "Castelo de São Jorge",
        "landmark",
        38.7139,
        -9.1335,
        30,
        {
            "description": "São Jorge Castle is a historic castle in Lisbon.",
            "opening_hours": "Mo-Su 09:00-21:00",
            "website": "https://castelodesaojorge.pt",
        },
    ),
    ("Praça do Comércio", "landmark", 38.7075, -9.1364, 31, {}),
    ("Sé de Lisboa", "religious", 38.7097, -9.1334, 25, {}),
    ("Elevador de Santa Justa", "landmark", 38.7121, -9.1394, 20, {}),
    ("Museu Calouste Gulbenkian", "museum", 38.7372, -9.1545, 20, {}),
    ("Museu Nacional do Azulejo", "museum", 38.7247, -9.1135, 15, {}),
    ("Arco da Rua Augusta", "monument", 38.7085, -9.1366, 12, {}),
    ("Panteão Nacional", "monument", 38.7150, -9.1247, 12, {}),
    ("Convento do Carmo", "religious", 38.7120, -9.1407, 10, {}),
    ("Mercado da Ribeira", "market", 38.7069, -9.1459, 8, {}),
    ("Jardim da Estrela", "park", 38.7136, -9.1597, 6, {}),
    ("Miradouro de Santa Luzia", "viewpoint", 38.7116, -9.1301, 5, {}),
    ("Miradouro de São Pedro de Alcântara", "viewpoint", 38.7155, -9.1444, 4, {}),
    ("Miradouro da Senhora do Monte", "viewpoint", 38.7192, -9.1327, 3, {}),
    # Places to eat, which plans never suggest: for the venue search, one within 2 km of
    # each sight.
    ("Tasca do Largo", "restaurant", 38.7150, -9.1290, 0, {"opening_hours": "Mo-Su 12:00-23:00"}),
    ("Café do Jardim", "cafe", 38.7250, -9.1560, 0, {"opening_hours": "Mo-Su 08:00-20:00"}),
]


def e2e_database_url(url: str) -> str:
    parsed = make_url(url)
    return parsed.set(database=f"{parsed.database}_e2e").render_as_string(hide_password=False)


async def create_database(url: str) -> None:
    parsed = make_url(url)
    engine = create_async_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    finally:
        await engine.dispose()


async def reset_and_seed() -> None:
    """Every run starts from the same places, with no plans, users or trips."""
    engine = create_engine()
    try:
        async with create_sessionmaker(engine)() as session, session.begin():
            await session.execute(text("TRUNCATE places, routes, users RESTART IDENTITY CASCADE"))
            categories = dict((await session.execute(select(Category.slug, Category.id))).all())
            session.add_all(
                Place(
                    osm_type="node",
                    osm_id=osm_id,
                    city="lisbon",
                    name=name,
                    category_id=categories[category],
                    geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
                    tags={"name": name},
                    wikidata=f"Q99{osm_id:05d}",
                    wikipedia_languages=languages,
                    **extra,
                )
                for osm_id, (name, category, lat, lon, languages, extra) in enumerate(PLACES, 1)
            )
    finally:
        await engine.dispose()


def migrations() -> Config:
    """alembic.ini's settings without its logging setup, which would print every line twice
    next to the app's."""
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    url = e2e_database_url(get_settings().database_url)
    asyncio.run(create_database(url))
    os.environ.update(
        DATABASE_URL=url,
        ROUTING_PROVIDER="haversine",
        TRANSIT_PROVIDER="estimate",
        OPENWEATHER_API_KEY="",
        AI_REQUESTS_PER_MINUTE="0",
        AI_REQUESTS_PER_DAY="0",
        LOG_LEVEL="WARNING",
    )
    get_settings.cache_clear()
    command.upgrade(migrations(), "head")
    asyncio.run(reset_and_seed())

    app = create_app()
    llm = e2e_llm()
    app.dependency_overrides[get_llm] = lambda: llm
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
