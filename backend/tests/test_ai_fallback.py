import asyncio
import logging

import pytest

from app.llm.base import LLMError, TransientLLMError
from app.llm.service import LLMService
from app.schemas.trip import TripRequest
from app.services.ai_fallback import (
    ask_llm,
    read_city,
    read_interests,
    read_keywords,
    read_pace,
    read_request,
)
from tests.fakes import FakeProvider
from tests.test_trip_schema import trip


def ask(llm: LLMService) -> TripRequest | None:
    return asyncio.run(ask_llm(llm, system="s", prompt="p", schema=TripRequest))


def test_ask_llm_answers_as_the_llm_does() -> None:
    llm = LLMService(FakeProvider().queue(trip()), model="m")
    assert ask(llm) == trip()


@pytest.mark.parametrize("error", [TransientLLMError("503"), LLMError("bad key")])
def test_ask_llm_answers_none_when_the_llm_fails(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    llm = LLMService(FakeProvider().queue(error), model="m", max_retries=0)
    with caplog.at_level(logging.WARNING):
        assert ask(llm) is None
    assert "without the LLM" in caplog.text or "planning without it" in caplog.text


def test_ask_llm_answers_none_when_the_budget_is_used_up() -> None:
    llm = LLMService(FakeProvider(), model="m")
    llm.budget.daily_limit = 0
    assert ask(llm) is None


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("A slow day in Lisbon", 1),
        ("2 days in Lisbon", 2),
        ("three-day trip to Berlin", 3),
        ("4 nights in Barcelona", 4),
        ("Two full days of museums", 2),
        ("48 hours in Berlin", 2),
        ("a weekend in Lisbon", 2),
        ("a long weekend in Lisbon", 3),
        ("a week of sightseeing", 7),
        ("12 days everywhere", 7),  # at most a week
        ("Lisbon with kids", 1),
    ],
)
def test_reads_the_days(text: str, days: int) -> None:
    assert read_request(text).days == days


def test_reads_interests_and_what_to_avoid() -> None:
    interests, avoid = read_interests(
        "We love museums, art galleries and views. No churches, please; avoid the markets."
    )
    assert interests == ["museum", "gallery", "viewpoint"]
    assert avoid == ["religious", "market"]


@pytest.mark.parametrize(
    "text", ["2 days in Barcelona", "baroque palaces in Berlin", "the Barrio Gótico"]
)
def test_a_word_names_an_interest_only_whole(text: str) -> None:
    assert "nightlife" not in read_interests(text)[0]


def test_food_and_drink_are_interests_too() -> None:
    # Plans never suggest them, but say so (app.services.place_selection.venue_notes).
    assert read_interests("Good food, coffee and a fado bar")[0] == [
        "restaurant",
        "cafe",
        "nightlife",
    ]


@pytest.mark.parametrize(
    ("text", "pace"),
    [
        ("Lisbon with kids, see everything", "relaxed"),
        ("A relaxed day", "relaxed"),
        ("Grandparents visiting", "relaxed"),
        ("I want to see everything", "intense"),
        ("As much as possible in one day", "intense"),
        ("2 days in Berlin", "moderate"),
    ],
)
def test_reads_the_pace(text: str, pace: str) -> None:
    assert read_pace(text) == pace


@pytest.mark.parametrize(
    ("text", "city"),
    [
        ("2 days in Lisbon", "lisbon"),
        ("Um dia em LISBOA", "lisbon"),
        ("Barcelona, then Berlin", "barcelona"),
        ("From Berlin to Barcelona", "berlin"),
        ("A weekend in Ulaanbaatar", None),
        ("Berliner Dom and more", None),
        ("Two days in NYC, then Washington DC", "new-york"),
        ("Washington, D.C. for the museums", "washington-dc"),
        ("Kyoto temples, then a day in Tokyo", "kyoto"),
        ("Ein Tag in München", "munich"),
        # Streets and squares named after a city are not the city.
        ("Washington Square, the High Line and SoHo", None),
    ],
)
def test_reads_the_first_supported_city(text: str, city: str | None) -> None:
    assert read_city(text) == city


@pytest.mark.parametrize(
    ("text", "keywords"),
    [
        ("2 days in Lisbon: viewpoints, the castle and Belém", ["Belém"]),
        ("We want the Torre de Belém and Alfama.", ["Torre de Belém", "Alfama"]),
        ("Gaudí's houses and the Sagrada Família in Barcelona", ["Sagrada Família"]),
        ("Museums in Berlin on Monday, then Museum Island", ["Museum Island"]),
        ("Belém first. Alfama next", []),  # sentence starts are no names
        ("I and We and You", []),
    ],
)
def test_reads_names_as_keywords(text: str, keywords: list[str]) -> None:
    assert read_keywords(text) == keywords


def test_reads_a_whole_request() -> None:
    assert read_request("3 days in Lisbon with kids: museums and the Oceanário, no churches") == (
        TripRequest(
            city="lisbon",
            days=3,
            interests=["museum"],
            avoid=["religious"],
            pace="relaxed",
            keywords=["Oceanário"],
            notes="",
        )
    )
