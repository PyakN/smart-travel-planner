from datetime import date
from zoneinfo import ZoneInfo

import pytest

from app.sun import daylight

LISBON = (38.7439, -9.1582)
LISBON_TZ = ZoneInfo("Europe/Lisbon")


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


@pytest.mark.parametrize(
    ("day", "sunrise", "sunset"),
    [
        # Lisbon's solstices: the longest day (in summer time) and the shortest.
        (date(2026, 6, 21), 6 * 60 + 12, 21 * 60 + 5),
        (date(2026, 12, 21), 7 * 60 + 51, 17 * 60 + 18),
    ],
)
def test_lisbon_daylight(day: date, sunrise: int, sunset: int) -> None:
    rise, set_ = daylight(day, *LISBON, LISBON_TZ)
    assert abs(rise - sunrise) <= 3, hhmm(rise)
    assert abs(set_ - sunset) <= 3, hhmm(set_)


def test_clock_change_moves_local_times() -> None:
    before = daylight(date(2026, 10, 24), *LISBON, LISBON_TZ)
    after = daylight(date(2026, 10, 25), *LISBON, LISBON_TZ)  # back to winter time
    # An hour for the clock, and a minute or so the evenings lose each day in October.
    assert 60 <= before[1] - after[1] <= 63
    assert 57 <= before[0] - after[0] <= 60


def test_polar_night_and_day() -> None:
    utc = ZoneInfo("UTC")
    rise, set_ = daylight(date(2026, 12, 21), 80.0, 15.0, utc)
    assert set_ - rise <= 1
    rise, set_ = daylight(date(2026, 6, 21), 80.0, 15.0, utc)
    assert set_ - rise >= 24 * 60 - 1
