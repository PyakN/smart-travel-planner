"""Whether a place is open at a given time, from its OpenStreetMap opening hours
(https://wiki.openstreetmap.org/wiki/Key:opening_hours), read by opening-hours-py.

About 3% of Lisbon's hours are not in the OSM syntax ("Segunda 08:00-20:00 ..."): those count
as unknown, like places without hours. Public holidays ("PH off") need the city's country,
and sunrise and sunset ("sunrise-sunset") the place's coordinates.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
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
# A trip day is read this far from its midnight: its hours may end the next morning.
SPAN_DAYS = 2
# When a place is open: from, until, in minutes since the midnight of a date.
Spans = tuple[tuple[int, int], ...]

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


def _minute(moment: datetime, on: date, city: City) -> int:
    """`moment` in minutes since the midnight of `on`, on the city's clock."""
    local = moment.astimezone(city.tz)
    return (local.date() - on).days * 24 * 60 + local.hour * 60 + local.minute


def open_spans(hours: OpeningHours, on: date, city: City) -> Spans | None:
    """When a place is open from the midnight of `on` for SPAN_DAYS days, in minutes since
    that midnight on the city's clock (past 24 * 60 the next day); empty when it is closed
    all that time. None when its hours leave part of it unknown."""
    begin = datetime.combine(on, time(), city.tz)
    end = datetime.combine(on + timedelta(days=SPAN_DAYS), time(), city.tz)
    spans: list[tuple[int, int]] = []
    for start, until, state, _ in hours.intervals(begin.astimezone(_UTC), end.astimezone(_UTC)):
        if state == State.UNKNOWN:
            return None
        if state != State.OPEN:
            continue
        a, b = _minute(start, on, city), _minute(until or end, on, city)
        if spans and spans[-1][1] == a:
            spans[-1] = (spans[-1][0], b)  # open across midnight
        else:
            spans.append((a, b))
    return tuple(spans)


def opening_by_date(
    raw: str | None, city: City, lat: float, lon: float, dates: Iterable[date]
) -> dict[date, Spans] | None:
    """A place's open spans (open_spans) on each of `dates` its hours tell; None when it has
    no hours that can be read."""
    hours = read_hours(raw, city, lat, lon)
    if hours is None:
        return None
    spans = {on: open_spans(hours, on, city) for on in dict.fromkeys(dates)}
    return {on: s for on, s in spans.items() if s is not None}
