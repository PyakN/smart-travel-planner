"""Accent- and case-insensitive name matching (needs the `unaccent` extension)."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, false, func, or_

from app.db.models import Place


def like_pattern(text: str, *, prefix: bool = False) -> str:
    """ILIKE pattern that matches `text` literally (`%` and `_` escaped with a backslash)."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%" if prefix else f"%{escaped}%"


def name_matches(terms: Sequence[str]) -> ColumnElement[bool]:
    """Place name or English name contains any of the terms."""
    if not terms:
        return false()
    haystacks = [Place.name, Place.tags["name:en"].astext]
    return or_(
        *(
            func.unaccent(haystack).ilike(func.unaccent(like_pattern(term)), escape="\\")
            for term in terms
            for haystack in haystacks
        )
    )
