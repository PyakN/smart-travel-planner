"""Schemas the LLM fills in. Kept free of numeric constraints (not every provider's
structured output supports them); values are normalized by validators instead."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.catalog import CategorySlug

Pace = Literal["relaxed", "moderate", "intense"]
STOPS_PER_DAY: dict[Pace, int] = {"relaxed": 4, "moderate": 6, "intense": 8}
MAX_DAYS = 7
MAX_KEYWORDS = 8
MAX_REQUEST_CHARS = 1000


class TripRequest(BaseModel):
    city: str | None = Field(
        description="City the traveller names, lowercase English (e.g. 'lisbon', 'tokyo'); "
        "null if none is mentioned"
    )
    days: int = Field(description="Number of sightseeing days; 1 if not mentioned")
    interests: list[CategorySlug] = Field(description="Categories the traveller wants")
    avoid: list[CategorySlug] = Field(description="Categories the traveller explicitly rejects")
    pace: Pace = Field(description="relaxed for kids/elderly/slow, intense for 'see everything'")
    keywords: list[str] = Field(
        description="Specific wishes as short search terms: place names, neighbourhoods, themes"
    )
    notes: str = Field(description="Other constraints in one short sentence, or empty")

    @field_validator("city")
    @classmethod
    def _normalize_city(cls, city: str | None) -> str | None:
        return city.strip().lower() or None if city else None

    @field_validator("days")
    @classmethod
    def _clamp_days(cls, days: int) -> int:
        return max(1, min(days, MAX_DAYS))

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, keywords: list[str]) -> list[str]:
        cleaned = [k.strip()[:50] for k in keywords if k.strip()]
        return list(dict.fromkeys(cleaned))[:MAX_KEYWORDS]

    @property
    def stops_target(self) -> int:
        return self.days * STOPS_PER_DAY[self.pace]


class PlaceSelection(BaseModel):
    place_ids: list[int] = Field(description="Chosen candidate ids, most important first")
    rationale: str = Field(description="One or two sentences on why this mix fits the request")
