from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.trip import MAX_DAYS, MAX_KEYWORDS, PlaceSelection, TripRequest, plain_text


def trip(**overrides: Any) -> TripRequest:
    fields: dict[str, Any] = {
        "city": "lisbon",
        "days": 2,
        "interests": ["viewpoint"],
        "avoid": [],
        "pace": "moderate",
        "keywords": [],
        "notes": "",
    }
    return TripRequest.model_validate(fields | overrides)


@pytest.mark.parametrize(("days", "expected"), [(0, 1), (-3, 1), (3, 3), (30, MAX_DAYS)])
def test_days_are_clamped(days: int, expected: int) -> None:
    assert trip(days=days).days == expected


@pytest.mark.parametrize(("city", "expected"), [(" Lisbon ", "lisbon"), ("", None), (None, None)])
def test_city_is_normalized(city: str | None, expected: str | None) -> None:
    assert trip(city=city).city == expected


def test_keywords_are_trimmed_deduplicated_and_capped() -> None:
    keywords = ["  Belém ", "Belém", "", "x" * 80] + [f"k{i}" for i in range(20)]
    cleaned = trip(keywords=keywords).keywords
    assert cleaned[:2] == ["Belém", "x" * 50]
    assert len(cleaned) == MAX_KEYWORDS


def test_html_entities_in_the_llms_text_are_decoded() -> None:
    # As Gemini answered a request for "Belém": the entity reached the plan as written.
    selection = PlaceSelection.model_validate(
        {
            "place_ids": [1, 2],
            "notes": [
                {"place_id": 1, "note": "A must-see waterfront landmark in Bel&eacute;m."},
                {"place_id": 2, "note": "Caf&#233; culture &amp; river views."},
            ],
            "rationale": "Highlights the historic Bel&eacute;m area.",
        }
    )
    assert [n.note for n in selection.notes] == [
        "A must-see waterfront landmark in Belém.",
        "Café culture & river views.",
    ]
    assert selection.rationale == "Highlights the historic Belém area."

    request = trip(keywords=["Bel&eacute;m", "Belém"], notes="Travelling with a caf&eacute; lover")
    # A search term like any other: it matches places named "Belém", and only once.
    assert request.keywords == ["Belém"]
    assert request.notes == "Travelling with a café lover"


@pytest.mark.parametrize("text", ["R&D", "Fish & chips", "Bread &nothing else", "AT&T;"])
def test_text_that_only_looks_like_an_entity_is_kept(text: str) -> None:
    assert plain_text(text) == text


def test_unknown_category_is_rejected() -> None:
    with pytest.raises(ValidationError):
        trip(interests=["nightclub"])
