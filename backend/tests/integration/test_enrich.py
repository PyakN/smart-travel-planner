"""Photo and description import against the test database, with Wikimedia mocked."""

import asyncio
from collections import Counter

import httpx
from sqlalchemy import select

from app.db.models import Place
from app.ingest.enrich import EnrichStats, WikiCache, enrich_city
from tests.integration.conftest import SessionFactory
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


def test_enrich_city(db_session: SessionFactory) -> None:
    cache, calls = WikiCache(), Counter[str]()
    stats = enrich(db_session, cache, calls)
    assert stats == EnrichStats(places=13, photos=1, descriptions=2)

    async def load() -> dict[str, tuple[str | None, str | None, str | None]]:
        async with db_session() as session:
            rows = await session.execute(
                select(Place.name, Place.description, Place.image_url, Place.image_credit).where(
                    Place.city == "testville"
                )
            )
            return {name: (d, url, credit) for name, d, url, credit in rows}

    places = asyncio.run(load())
    assert places["Testville Cathedral"] == (
        "A cathedral. It is big.",
        "https://thumb.wikimedia.org/x/500px-Cathedral.jpg",
        "Jane, CC BY-SA 4.0",
    )
    assert places["Old Town Square"] == ("Square in Testville.", None, None)
    assert places["Clock Tower"] == (None, None, None)

    # Answers and misses are cached: a second run asks nothing.
    assert cache.wikidata["Q900004"] is None
    calls.clear()
    assert enrich(db_session, cache, calls) == stats
    assert not calls
