"""Photo and description import against the test database, with Wikimedia mocked."""

import asyncio
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, update

from app.db.models import Place
from app.ingest.enrich import EnrichStats, WikiCache, enrich_city
from app.ingest.wiki import WikidataInfo
from tests.integration.conftest import SEED_FAME, SessionFactory
from tests.test_wiki import binding, imageinfo_page

CATHEDRAL_IMAGE = "https://commons.wikimedia.org/wiki/Special:FilePath/Cathedral.jpg"


def wikimedia(calls: Counter[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls[request.url.host] += 1
        if request.url.host == "query.wikidata.org":
            bindings = [
                binding(
                    "Q900001",
                    image=CATHEDRAL_IMAGE,
                    article="https://en.wikipedia.org/wiki/Testville_Cathedral",
                    wikipedias="12",
                ),
                binding("Q900002", description="square in Testville"),
            ]
            return httpx.Response(200, json={"results": {"bindings": bindings}})
        if request.url.host == "commons.wikimedia.org":
            return httpx.Response(
                200, json={"query": {"pages": [imageinfo_page("File:Cathedral.jpg")]}}
            )
        pages = [
            {"title": "Testville Cathedral", "extract": "A cathedral (built 1200). It is big."}
        ]
        return httpx.Response(200, json={"query": {"pages": pages}})

    return httpx.MockTransport(handler)


def enrich(db_session: SessionFactory, cache: WikiCache, calls: Counter[str]) -> EnrichStats:
    async def run() -> EnrichStats:
        async with db_session() as session, httpx.AsyncClient(transport=wikimedia(calls)) as client:
            return await enrich_city(session, client, "testville", cache)

    return asyncio.run(run())


@pytest.fixture
def seeded_fame_afterwards(db_session: SessionFactory) -> Iterator[None]:
    """Enriching rewrites the places' fame, and later tests rank candidates by it."""
    yield

    async def restore() -> None:
        async with db_session() as session:
            for qid, languages in SEED_FAME.items():
                await session.execute(
                    update(Place).where(Place.wikidata == qid).values(wikipedia_languages=languages)
                )
            await session.commit()

    asyncio.run(restore())


@pytest.mark.usefixtures("seeded_fame_afterwards")
def test_enrich_city(db_session: SessionFactory) -> None:
    cache, calls = WikiCache(), Counter[str]()
    stats = enrich(db_session, cache, calls)
    assert stats == EnrichStats(places=23, photos=1, descriptions=2, in_wikipedia=1)

    async def load() -> dict[str, tuple[str | None, str | None, str | None, int]]:
        async with db_session() as session:
            rows = await session.execute(
                select(
                    Place.name,
                    Place.description,
                    Place.image_url,
                    Place.image_credit,
                    Place.wikipedia_languages,
                ).where(Place.city == "testville")
            )
            return {name: (d, url, credit, n) for name, d, url, credit, n in rows}

    places = asyncio.run(load())
    assert places["Testville Cathedral"] == (
        "A cathedral. It is big.",
        "https://thumb.wikimedia.org/x/500px-Cathedral.jpg",
        "Jane, CC BY-SA 4.0",
        12,
    )
    assert places["Old Town Square"] == ("Square in Testville.", None, None, 0)
    assert places["Clock Tower"] == (None, None, None, 0)

    # Answers and misses are cached: a second run asks nothing.
    assert cache.wikidata["Q900004"] is None
    calls.clear()
    assert enrich(db_session, cache, calls) == stats
    assert not calls


def test_cache_asks_again_for_items_saved_without_a_count(tmp_path: Path) -> None:
    path = tmp_path / "testville-wiki.json"
    counted = {"image": None, "description": None, "article": None, "wikipedias": 3}
    old = {"image": "Old.jpg", "description": None, "article": None}
    raw = {"wikidata": {"Q1": counted, "Q2": old, "Q3": None}, "photos": {}, "extracts": {}}
    path.write_text(json.dumps(raw), encoding="utf-8")

    cache = WikiCache.load(path)
    assert cache.wikidata == {"Q1": WikidataInfo(None, None, None, 3), "Q3": None}
