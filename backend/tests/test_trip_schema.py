from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.trip import MAX_DAYS, MAX_KEYWORDS, TripRequest


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


def test_unknown_category_is_rejected() -> None:
    with pytest.raises(ValidationError):
        trip(interests=["nightclub"])


def test_stops_target_depends_on_pace() -> None:
    assert trip(days=2, pace="relaxed").stops_target == 8
    assert trip(days=1, pace="intense").stops_target == 8
