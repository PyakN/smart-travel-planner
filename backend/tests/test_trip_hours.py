"""The hours of a trip's days, from what the traveller asked for and the time now."""

from datetime import date, datetime, time

import pytest

from app.ingest.cities import CITIES
from app.optimizer.planner import DayWindow
from app.schemas.plan import PlanRequest
from app.services.day_hours import DailyHours, trip_windows
from app.services.place_selection import PlanningError, day_places
from app.services.trip_planner import late_start_warnings

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


def test_each_day_has_its_own_hours() -> None:
    hours = DailyHours(time(8), time(20), each=((time(10), time(18)), (time(16), time(3))))
    first, second = windows(hours, days=2)
    assert (first.start_min, first.end_min) == (10 * H, 18 * H)
    assert (second.start_min, second.end_min) == (16 * H, 27 * H)  # until 03:00 the next day
    assert (first.on, second.on) == (WEDNESDAY, date(2026, 10, 29))


def test_a_day_of_its_own_hours_needs_time() -> None:
    hours = DailyHours(each=((time(10), time(18)), (time(17), time(17, 30))))
    with pytest.raises(PlanningError, match="Day 2 from 17:00 to 17:30 is too short"):
        windows(hours, days=2)


def test_a_day_ends_before_the_next_one_starts() -> None:
    late = DailyHours(each=((time(16), time(3)), (time(2), time(12))))
    with pytest.raises(PlanningError, match="Day 1 ends at 03:00 the next day, after day 2"):
        windows(late, days=2)
    first, second = windows(DailyHours(each=((time(16), time(3)), (time(3), time(12)))), days=2)
    assert first.end_min - 24 * H == second.start_min  # one ends as the other starts


def test_today_starts_no_earlier_than_now() -> None:
    today = TUESDAY_4PM.date()
    [day] = windows(DailyHours(), first=today)
    assert day.start_min == 16 * H + 15  # the next quarter of an hour
    [later] = windows(DailyHours(first_start=time(18)), first=today)
    assert later.start_min == 18 * H
    tomorrow = windows(DailyHours(), days=2, first=today)[1]
    assert tomorrow.start_min == 9 * H + 30
    own = DailyHours(each=((time(10), time(21)), (time(11), time(21))))
    first, second = windows(own, days=2, first=today)
    assert (first.start_min, second.start_min) == (16 * H + 15, 11 * H)
    assert late_start_warnings(own, [first, second]) == [
        "Day 1 starts at 16:15: it is past 10:00 already."
    ]


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
        "day_hours": [],
    }
    each = DailyHours(each=((time(10), time(18)), (time(16), time(3))))
    assert each.as_params()["day_hours"] == [
        {"start": "10:00", "end": "18:00"},
        {"start": "16:00", "end": "03:00"},
    ]


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


def test_hours_for_each_day() -> None:
    hours = [{"start": "10:00", "end": "18:00"}, {"start": "16:00", "end": "03:00"}]
    request = PlanRequest.model_validate({"text": "Two days", "day_hours": hours})
    assert request.day_count == 2  # one day per hours
    assert [(h.start, h.end) for h in request.day_hours] == [
        (time(10), time(18)),
        (time(16), time(3)),
    ]
    assert PlanRequest(text="Three days", day_count=3).day_hours == []


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"day_count": 3}, "one entry per day"),
        ({"first_day_start": "12:00"}, "the first day starts at day_hours"),
        ({"day_hours": [{"start": "10:00", "end": "10:00"}]}, "end must differ"),
    ],
)
def test_hours_for_each_day_must_fit_the_days(body: dict[str, object], error: str) -> None:
    hours = [{"start": "10:00", "end": "18:00"}, {"start": "16:00", "end": "03:00"}]
    with pytest.raises(ValueError, match=error):
        PlanRequest.model_validate({"text": "Two days", "day_hours": hours} | body)
