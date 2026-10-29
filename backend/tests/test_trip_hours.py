"""The hours of a trip's days, from what the traveller asked for and the time now."""

from datetime import date, datetime, time

import pytest

from app.ingest.cities import CITIES
from app.optimizer.planner import DayWindow
from app.schemas.plan import PlanRequest
from app.services.day_hours import DailyHours, trip_windows
from app.services.place_selection import PlanningError, day_places

LISBON = CITIES["lisbon"]
WEDNESDAY = date(2026, 10, 28)
# Tuesday afternoon, the day before.
TUESDAY_4PM = datetime(2026, 10, 27, 16, 7, tzinfo=LISBON.tz)
H = 60


def windows(hours: DailyHours, days: int = 1, first: date = WEDNESDAY) -> list[DayWindow]:
    return trip_windows(hours, LISBON, first, days, TUESDAY_4PM)


def test_default_hours_and_daylight() -> None:
    [day] = windows(DailyHours())
    assert (day.start_min, day.end_min) == (9 * H + 30, 21 * H + 30)
    assert day.sunrise_min is not None and day.sunset_min is not None
    assert 6 * H + 55 <= day.sunrise_min <= 7 * H + 5
    assert 17 * H + 35 <= day.sunset_min <= 17 * H + 45


def test_a_day_that_ends_after_midnight() -> None:
    [day] = windows(DailyHours(time(16), time(3)))
    assert (day.start_min, day.end_min) == (16 * H, 27 * H)


def test_only_the_first_day_starts_later() -> None:
    first, second = windows(DailyHours(first_start=time(16)), days=2)
    assert (first.start_min, second.start_min) == (16 * H, 9 * H + 30)
    assert first.end_min == second.end_min
    assert first.sunset_min != second.sunset_min  # each date has its daylight
    assert (first.on, second.on) == (WEDNESDAY, date(2026, 10, 29))  # and opening hours


def test_today_starts_no_earlier_than_now() -> None:
    today = TUESDAY_4PM.date()
    [day] = windows(DailyHours(), first=today)
    assert day.start_min == 16 * H + 15  # the next quarter of an hour
    [later] = windows(DailyHours(first_start=time(18)), first=today)
    assert later.start_min == 18 * H
    tomorrow = windows(DailyHours(), days=2, first=today)[1]
    assert tomorrow.start_min == 9 * H + 30


def test_today_is_over() -> None:
    with pytest.raises(PlanningError, match="too late for today's hours"):
        windows(DailyHours(end=time(17)), first=TUESDAY_4PM.date())


@pytest.mark.parametrize(
    "hours",
    [
        DailyHours(time(10), time(10, 30)),
        DailyHours(first_start=time(21)),
        DailyHours(time(9, 30), time(3), first_start=time(2)),
    ],
)
def test_hours_that_leave_no_day(hours: DailyHours) -> None:
    with pytest.raises(PlanningError, match="Day 1 from"):
        windows(hours)


def test_hours_are_saved_as_clock_times() -> None:
    assert DailyHours(time(16), time(3), first_start=time(17, 45)).as_params() == {
        "day_start": "16:00",
        "day_end": "03:00",
        "first_day_start": "17:45",
    }


def test_places_per_day_follow_the_hours() -> None:
    assert day_places(DayWindow(), "moderate") == 6
    assert day_places(DayWindow(), "relaxed") == 4
    assert day_places(DayWindow(16 * H, 21 * H + 30), "moderate") == 3  # instead of 6
    assert day_places(DayWindow(16 * H, 27 * H), "moderate") == 6
    assert day_places(DayWindow(20 * H, 21 * H), "relaxed") == 1


def test_a_day_needs_an_end_and_a_start() -> None:
    with pytest.raises(ValueError, match="day_end must differ"):
        PlanRequest(text="A day", day_start=time(10), day_end=time(10))
    overnight = PlanRequest.model_validate({"text": "A night", "day_end": "03:00"})
    assert (overnight.day_start, overnight.day_end) == (time(9, 30), time(3))
