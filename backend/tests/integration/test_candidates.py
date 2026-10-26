import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import CATEGORY_SLUGS
from app.db.models import Category
from app.repositories.candidates import Candidate, find_candidates

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def candidates(db_session: SessionFactory, **kwargs: Any) -> list[Candidate]:
    async def run() -> list[Candidate]:
        async with db_session() as session:
            return await find_candidates(session, city="lisbon", **kwargs)

    return asyncio.run(run())


def names(found: list[Candidate]) -> list[str]:
    return [c.name for c in found]


def test_catalog_matches_seeded_categories(db_session: SessionFactory) -> None:
    async def run() -> list[str]:
        async with db_session() as session:
            return list((await session.scalars(select(Category.slug).order_by(Category.id))).all())

    assert tuple(asyncio.run(run())) == CATEGORY_SLUGS


def test_notable_places_rank_first(db_session: SessionFactory) -> None:
    found = candidates(db_session)
    assert names(found)[0] == "Torre de Belém"  # wikidata + wikipedia
    assert names(found)[-1] in {"Miradouro de Santa Luzia", "Museu Calouste Gulbenkian"}
    assert "Museu de Serralves" not in names(found)  # Porto


def test_interest_boost(db_session: SessionFactory) -> None:
    assert names(candidates(db_session, interests=["viewpoint"]))[:2] == [
        "Torre de Belém",
        "Miradouro de Santa Luzia",
    ]
    assert names(candidates(db_session, interests=["museum"]))[1] == "Museu Calouste Gulbenkian"


def test_keyword_is_accent_insensitive_and_matches_english_name(
    db_session: SessionFactory,
) -> None:
    for keyword in ("belem", "BELEM TOWER", "Castelo de Sao Jorge"):
        top = candidates(db_session, keywords=[keyword])[0]
        assert top.score >= 4, keyword
    assert candidates(db_session, keywords=["sao jorge"])[0].name == "Castelo de São Jorge"


def test_avoid_excludes_category_unless_named(db_session: SessionFactory) -> None:
    found = names(candidates(db_session, avoid=["landmark"], keywords=["castelo"]))
    assert "Castelo de São Jorge" in found
    assert "Praça do Comércio" not in found
    assert "Torre de Belém" not in found


def test_like_wildcards_in_keywords_are_literal(db_session: SessionFactory) -> None:
    assert all(c.score < 4 for c in candidates(db_session, keywords=["%", "_"]))


def test_hint_uses_english_name(db_session: SessionFactory) -> None:
    torre = next(c for c in candidates(db_session) if c.name == "Torre de Belém")
    assert torre.hint == "Belém Tower"


def test_limit(db_session: SessionFactory) -> None:
    assert len(candidates(db_session, limit=2)) == 2
