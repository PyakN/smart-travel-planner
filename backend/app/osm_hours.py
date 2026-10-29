"""Whether a place is open at a given time, from its OpenStreetMap opening hours
(https://wiki.openstreetmap.org/wiki/Key:opening_hours), read by opening-hours-py.

About 3% of Lisbon's hours are not in the OSM syntax ("Segunda 08:00-20:00 ..."): those count
as unknown, like places without hours. Public holidays ("PH off") need the city's country,
and sunrise and sunset ("sunrise-sunset") the place's coordinates.
"""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

# ParserError is what parsing raises, but its stubs leave it out.
from opening_hours import (  # type: ignore[attr-defined]
    OpeningHours,
    ParserError,
    State,
)

from app.ingest.cities import City

OpenState = Literal["open", "closed", "unknown"]
# How far ahead to look for the next change: a place closed for longer counts as closed
# for good. Enough for "opens on Monday", and it keeps odd hours fast to evaluate.
LOOKAHEAD_DAYS = 8

# The parser takes moments in IANA time zones only (not datetime.UTC).
_UTC = ZoneInfo("UTC")
_STATES: dict[State, OpenState] = {
    State.OPEN: "open",
    State.CLOSED: "closed",
    State.UNKNOWN: "unknown",
}


def read_hours(raw: str | None, city: City, lat: float, lon: float) -> OpeningHours | None:
    """A place's opening hours in its city's time; None when it has none, or they cannot be
    read."""
    if not raw or not raw.strip():
        return None
    try:
        return OpeningHours(
            raw,
            timezone=city.tz,
            country=city.country,
            coords=(lat, lon),
            max_interval_days=LOOKAHEAD_DAYS,
        )
    except ParserError:
        return None


def open_state(hours: OpeningHours | None, at: datetime) -> OpenState:
    """Open, closed or unknown at `at` (an aware datetime)."""
    return _STATES[hours.state(at.astimezone(_UTC))[0]] if hours else "unknown"


def next_change(hours: OpeningHours | None, at: datetime) -> datetime | None:
    """When the state at `at` (an aware datetime) changes next, in the city's time; None
    when unknown, or not within LOOKAHEAD_DAYS (open 24/7, closed for the season)."""
    return hours.next_change(at.astimezone(_UTC)) if hours else None
