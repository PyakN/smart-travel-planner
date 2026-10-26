"""End-to-end selection pipeline against the seeded database, with a scripted LLM."""

import asyncio

from app.llm.service import LLMService
from app.schemas.trip import PlaceSelection
from app.services.place_selection import SelectionResult, select_places
from tests.fakes import FakeProvider
from tests.integration.conftest import SessionFactory
from tests.test_trip_schema import trip


def run(db_session: SessionFactory, provider: FakeProvider, text: str) -> SelectionResult:
    async def go() -> SelectionResult:
        async with db_session() as session:
            llm = LLMService(provider, model="m")
            return await select_places(llm, session, text, default_city="lisbon")

    return asyncio.run(go())


def test_pipeline_returns_only_real_places(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    castelo, luzia = place_ids["Castelo de São Jorge"], place_ids["Miradouro de Santa Luzia"]
    provider = FakeProvider().queue(
        trip(city=None, days=1, pace="relaxed", interests=["viewpoint"]),
        # One hallucinated id and one from Porto, which is not a Lisbon candidate.
        PlaceSelection(
            place_ids=[luzia, 424242, castelo, place_ids["Museu de Serralves"]],
            rationale="Views first.",
        ),
    )
    result = run(db_session, provider, "A slow day in Lisbon, love views")

    assert result.city == "lisbon"  # default applied
    assert [p.name for p in result.places][:2] == [
        "Miradouro de Santa Luzia",
        "Castelo de São Jorge",
    ]
    assert len(result.places) == 4  # relaxed: 4 stops/day, 2 backfilled
    assert {p.id for p in result.places} <= {
        p for n, p in place_ids.items() if n != "Museu de Serralves"
    }
    assert "dropped 2 id(s) not in the candidate list" in result.warnings
    assert result.candidates_considered == 5

    # The selection prompt lists the candidates the LLM may choose from.
    selection_prompt = str(provider.calls[1]["prompt"])
    assert f"{luzia} | Miradouro de Santa Luzia | viewpoint" in selection_prompt
    assert "Serralves" not in selection_prompt
