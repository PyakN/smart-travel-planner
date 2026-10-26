"""Import a city's points of interest from OpenStreetMap.

Usage (from backend/):  python -m app.ingest lisbon [--refresh]
"""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from geoalchemy2 import WKTElement
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Category, Place
from app.db.session import create_engine, create_sessionmaker
from app.ingest.cities import CITIES, City
from app.ingest.osm import PlaceRecord, build_query, deduplicate, fetch_elements, parse_elements

# Raw Overpass responses are cached so re-runs don't hit the public API.
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
BATCH_SIZE = 500
UPDATED_COLUMNS = (
    "city",
    "name",
    "category_id",
    "geom",
    "tags",
    "wikidata",
    "opening_hours",
    "website",
)


async def load_elements(city: City, refresh: bool) -> list[dict[str, Any]]:
    cache_file = CACHE_DIR / f"{city.slug}.json"
    if cache_file.exists() and not refresh:
        print(f"Using cached Overpass response: {cache_file}")
        elements: list[dict[str, Any]] = json.loads(cache_file.read_text(encoding="utf-8"))
        return elements

    print(f"Querying Overpass for {city.name}...")
    async with httpx.AsyncClient() as client:
        elements = await fetch_elements(build_query(city.bbox), client)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(elements, ensure_ascii=False), encoding="utf-8")
    return elements


def to_row(record: PlaceRecord, city: City, category_ids: dict[str, int]) -> dict[str, Any]:
    return {
        "osm_type": record.osm_type,
        "osm_id": record.osm_id,
        "city": city.slug,
        "name": record.name,
        "category_id": category_ids[record.category],
        "geom": WKTElement(f"POINT({record.lon} {record.lat})", srid=4326),
        "tags": record.tags,
        "wikidata": record.wikidata,
        "opening_hours": record.opening_hours,
        "website": record.website,
    }


async def import_city(city: City, refresh: bool) -> None:
    elements = await load_elements(city, refresh)
    parsed = parse_elements(elements)
    records = deduplicate(parsed)
    print(f"{len(elements)} OSM elements -> {len(parsed)} places -> {len(records)} after dedup")

    engine = create_engine()
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session, session.begin():
            result = await session.execute(select(Category.slug, Category.id))
            category_ids = {slug: category_id for slug, category_id in result}
            rows = [to_row(r, city, category_ids) for r in records]
            for start in range(0, len(rows), BATCH_SIZE):
                stmt = insert(Place).values(rows[start : start + BATCH_SIZE])
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_places_osm",
                    set_={col: stmt.excluded[col] for col in UPDATED_COLUMNS}
                    | {"updated_at": func.now()},
                )
                await session.execute(stmt)
    finally:
        await engine.dispose()

    for category, count in Counter(r.category for r in records).most_common():
        print(f"  {category:<12} {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", choices=sorted(CITIES))
    parser.add_argument("--refresh", action="store_true", help="ignore the cached response")
    args = parser.parse_args()
    asyncio.run(import_city(CITIES[args.city], args.refresh))


if __name__ == "__main__":
    main()
