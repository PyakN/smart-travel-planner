import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import CATEGORY_SLUGS
from app.db.models import Category
from app.optimizer.geometry import LatLon
from app.repositories.candidates import Candidate, find_candidates, get_candidates

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


def test_candidates_say_whether_they_are_outdoors(db_session: SessionFactory) -> None:
    outdoor = {c.name: c.outdoor for c in candidates(db_session)}
    assert outdoor["Miradouro de Santa Luzia"] is True
    assert outdoor["Castelo de São Jorge"] is True
    assert outdoor["Museu Calouste Gulbenkian"] is False


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


def test_coordinates(db_session: SessionFactory) -> None:
    luzia = next(c for c in candidates(db_session) if c.name == "Miradouro de Santa Luzia")
    assert (luzia.lat, luzia.lon) == (38.7116, -9.1301)


def test_limit(db_session: SessionFactory) -> None:
    assert len(candidates(db_session, limit=2)) == 2


PRACA = LatLon(38.7075, -9.1364)


def test_places_near_an_anchor_rank_first(db_session: SessionFactory) -> None:
    # Without anchors: Torre de Belém (Wikidata + Wikipedia), then the other notable places.
    found = candidates(db_session, anchors=[PRACA], proximity_radius_m=2500)
    assert names(found) == [
        "Praça do Comércio",  # at the anchor
        "Castelo de São Jorge",  # 0.8 km
        "Torre de Belém",  # 7 km: no boost, still the most notable
        "Miradouro de Santa Luzia",  # 0.7 km, not notable
        "Museu Calouste Gulbenkian",  # 3.5 km: no boost
    ]
    assert found[0].distance_m == pytest.approx(0, abs=0.01)
    assert found[2].score == 3.0  # notability only
    assert all(c.distance_m is None for c in candidates(db_session))

    # A nearby match for the traveller's interests beats a famous place far away.
    viewpoints = candidates(db_session, anchors=[PRACA], interests=["viewpoint"])
    assert names(viewpoints)[:3] == [
        "Praça do Comércio",
        "Miradouro de Santa Luzia",
        "Castelo de São Jorge",
    ]


def test_nearest_anchor_counts(db_session: SessionFactory) -> None:
    belem = LatLon(38.6916, -9.2160)
    found = candidates(db_session, anchors=[PRACA, belem])
    assert {names(found)[0], names(found)[1]} == {"Praça do Comércio", "Torre de Belém"}


def test_excluded_ids_are_left_out(db_session: SessionFactory, place_ids: dict[str, int]) -> None:
    found = candidates(db_session, exclude_ids=[place_ids["Torre de Belém"]])
    assert "Torre de Belém" not in names(found)
    assert len(found) == 4


def test_get_candidates_keeps_order_and_city(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    wanted = [
        place_ids["Miradouro de Santa Luzia"],
        place_ids["Museu de Serralves"],  # Porto
        424242,  # unknown
        place_ids["Castelo de São Jorge"],
    ]

    async def run() -> list[Candidate]:
        async with db_session() as session:
            return await get_candidates(session, wanted, city="lisbon")

    assert names(asyncio.run(run())) == ["Miradouro de Santa Luzia", "Castelo de São Jorge"]
