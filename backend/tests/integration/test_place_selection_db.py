"""End-to-end selection pipeline against the seeded database, with a scripted LLM."""

import asyncio
from typing import Any

import pytest

from app.ingest.cities import City
from app.llm.service import LLMService
from app.optimizer.geometry import LatLon
from app.schemas.trip import PlaceNote, PlaceSelection
from app.services.place_selection import PlanningError, SelectionResult, select_places
from app.services.weather_service import TripWeather, parse_forecast, trip_weather
from tests.fakes import FakeProvider
from tests.integration.conftest import SessionFactory
from tests.test_trip_schema import trip
from tests.test_weather_service import WEDNESDAY, fixture


def run(
    db_session: SessionFactory, provider: FakeProvider, text: str, **kwargs: Any
) -> SelectionResult:
    async def go() -> SelectionResult:
        async with db_session() as session:
            llm = LLMService(provider, model="m")
            return await select_places(llm, session, text, default_city="lisbon", **kwargs)

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


def test_must_visit_places_come_first_and_anchor_the_rest(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    gulbenkian, luzia = (
        place_ids["Museu Calouste Gulbenkian"],
        place_ids["Miradouro de Santa Luzia"],
    )
    provider = FakeProvider().queue(
        trip(city=None, days=1, pace="relaxed", interests=["viewpoint"]),
        PlaceSelection(place_ids=[luzia, gulbenkian], rationale="Views."),
    )
    hotel = LatLon(38.7075, -9.1364)  # Praça do Comércio
    result = run(db_session, provider, "A slow day", must_visit=[gulbenkian], start=hotel)

    assert [p.name for p in result.must_visit] == ["Museu Calouste Gulbenkian"]
    assert result.places[0].id == gulbenkian
    assert result.places[1].id == luzia
    # The LLM's repeat of the must-visit is not a candidate: dropped and backfilled once.
    assert len(result.places) == 3
    assert len({p.id for p in result.places}) == 3
    assert "dropped 1 id(s) not in the candidate list" in result.warnings

    prompt = str(provider.calls[1]["prompt"])
    must_line = f"- {gulbenkian} | Museu Calouste Gulbenkian | museum"
    assert f"Must-visit places (already in the plan):\n{must_line}\n" in prompt
    assert "Number of places to choose: 3" in prompt
    assert "(id | name | category | distance | hint)" in prompt
    assert f"{luzia} | Miradouro de Santa Luzia | viewpoint | 0.7 km" in prompt
    assert prompt.count(f"{gulbenkian} |") == 1  # listed as must-visit, not as a candidate


def test_must_visit_places_can_fill_the_trip(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    names = (
        "Castelo de São Jorge",
        "Torre de Belém",
        "Praça do Comércio",
        "Museu Calouste Gulbenkian",
    )
    must = [place_ids[n] for n in names]
    provider = FakeProvider().queue(trip(city=None, days=1, pace="relaxed"))
    result = run(db_session, provider, "Just these", must_visit=must + must[:2])  # repeats ignored
    assert [p.id for p in result.places] == must  # a relaxed day holds 4 stops
    assert len(provider.calls) == 1  # nothing left to choose: no selection call


async def rainy_wednesday(city: City, days: int) -> TripWeather:
    """Dry only until 10:30: a sixth of a relaxed day's sightseeing hours."""
    return trip_weather(parse_forecast(fixture()), WEDNESDAY, days, city.tz)


def queue_four_outdoor_picks(place_ids: dict[str, int]) -> FakeProvider:
    picks = ["Miradouro de Santa Luzia", "Castelo de São Jorge", "Praça do Comércio"]
    return FakeProvider().queue(
        trip(city=None, days=1, pace="relaxed", interests=["viewpoint"]),
        PlaceSelection(
            place_ids=[place_ids[name] for name in (*picks, "Torre de Belém")],
            notes=[PlaceNote(place_id=place_ids["Torre de Belém"], note="Iconic.")],
            rationale="Views.",
        ),
    )


def test_weather_aware_selection_makes_room_for_the_rain(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    provider = queue_four_outdoor_picks(place_ids)
    result = run(db_session, provider, "A slow day", weather=rainy_wednesday, weather_aware=True)

    prompt = str(provider.calls[1]["prompt"])
    assert (
        "- Day 1, Wed 28 Oct: moderate rain 10:30-15:30 (up to 91%); 16-17 °C; "
        "daylight 07:03-17:37" in prompt
    )
    assert "Choose at most 1 outdoor place. For the rest prefer indoor places" in prompt
    luzia = place_ids["Miradouro de Santa Luzia"]
    gulbenkian = place_ids["Museu Calouste Gulbenkian"]
    lines = prompt.splitlines()
    assert f"{luzia} | Miradouro de Santa Luzia | viewpoint, outdoor" in lines
    assert f"{gulbenkian} | Museu Calouste Gulbenkian | museum, indoor" in lines

    # The LLM chose four outdoor places; the only indoor one takes the least important's slot.
    assert [p.name for p in result.places][-1] == "Museu Calouste Gulbenkian"
    assert [(a.name, b.name) for a, b in result.weather_swaps] == [
        ("Torre de Belém", "Museu Calouste Gulbenkian")
    ]
    assert place_ids["Torre de Belém"] not in result.notes  # its note left with it
    assert result.weather is not None and result.weather.days[0].date == WEDNESDAY


def test_without_weather_awareness_the_weather_is_only_returned(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    provider = queue_four_outdoor_picks(place_ids)
    result = run(db_session, provider, "A slow day", weather=rainy_wednesday)
    prompt = str(provider.calls[1]["prompt"])
    assert "outdoor" not in prompt and "Weather" not in prompt
    assert [p.name for p in result.places][-1] == "Torre de Belém"
    assert result.weather_swaps == []
    assert result.weather is not None


def test_unknown_must_visit_place_is_rejected(
    db_session: SessionFactory, place_ids: dict[str, int]
) -> None:
    provider = FakeProvider().queue(trip(city=None))
    with pytest.raises(PlanningError, match="not in Lisbon"):
        run(db_session, provider, "A day", must_visit=[place_ids["Museu de Serralves"]])
