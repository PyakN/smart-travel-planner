"""Schemas the LLM fills in. Kept free of numeric constraints (not every provider's
structured output supports them); values are normalized by validators instead."""

import html
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.catalog import CategorySlug

Pace = Literal["relaxed", "moderate", "intense"]
# Places in a day of the default hours (app.services.place_selection.day_places).
STOPS_PER_DAY: dict[Pace, int] = {"relaxed": 4, "moderate": 6, "intense": 8}
MAX_DAYS = 7
MAX_KEYWORDS = 8
MAX_REQUEST_CHARS = 1000

# Complete character references only: "&eacute;" or "&#233;", never the "&not" of "&nothing".
_CHAR_REFERENCE = re.compile(r"&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]*);", re.IGNORECASE)


def plain_text(text: str) -> str:
    """`text` with HTML character references decoded: models sometimes write "Bel&eacute;m"."""
    return _CHAR_REFERENCE.sub(lambda m: html.unescape(m[0]), text)


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
        cleaned = [plain_text(k).strip()[:50] for k in keywords if k.strip()]
        return list(dict.fromkeys(cleaned))[:MAX_KEYWORDS]

    @field_validator("notes")
    @classmethod
    def _plain_notes(cls, notes: str) -> str:
        return plain_text(notes)


class PlaceNote(BaseModel):
    place_id: int
    note: str = Field(description="Why this place suits this traveller, at most 20 words")

    @field_validator("note")
    @classmethod
    def _plain_note(cls, note: str) -> str:
        return plain_text(note)


class PlaceSelection(BaseModel):
    place_ids: list[int] = Field(description="Chosen candidate ids, most important first")
    notes: list[PlaceNote] = Field(
        default_factory=list, description="One note per chosen place and per must-visit place"
    )
    rationale: str = Field(description="One or two sentences on why this mix fits the request")

    @field_validator("rationale")
    @classmethod
    def _plain_rationale(cls, rationale: str) -> str:
        return plain_text(rationale)
