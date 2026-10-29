"""The hours of a trip's days: the traveller's daily hours or each day's own, a first day
that starts later (today: from now on), and every day's daylight.

Times are the city's wall clock in minutes since midnight of each trip day, as in the
optimizer; a day that ends after midnight ends past 24 * 60.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Any

from app.ingest.cities import City
from app.optimizer.planner import MINUTES_PER_DAY, DayWindow
from app.services.place_selection import PlanningError
from app.services.weather_service import city_point, hhmm
from app.sun import daylight

# A day needs this long for one visit and the way there.
MIN_DAY_MIN = 60
# A trip that starts today starts at the next quarter of an hour.
NOW_STEP_MIN = 15


def minute_of(moment: time) -> int:
    return moment.hour * 60 + moment.minute


@dataclass(frozen=True)
class DailyHours:
    """The traveller's hours: every day from `start` to `end` (the next morning when `end`
    is not after `start`), and the first day from `first_start` if that is given. Days in
    `each` (day 1 first) have their own (start, end) instead."""

    start: time = time(9, 30)
    end: time = time(21, 30)
    first_start: time | None = None
    each: tuple[tuple[time, time], ...] = ()

    def of_day(self, index: int) -> tuple[int, int]:
        """Start and end of day `index` (0 is the first) in minutes; an end the next
        morning is past 24 * 60."""
        if index < len(self.each):
            start, end = map(minute_of, self.each[index])
        else:
            # A later first start keeps the days' end: 09:30 to 21:30 from 16:00 ends at 21:30.
            start, end = minute_of(self.start), minute_of(self.end)
        if end <= start:
            end += MINUTES_PER_DAY
        if index == 0 and self.first_start is not None and not self.each:
            start = minute_of(self.first_start)
        return start, end

    def as_params(self) -> dict[str, Any]:
        return {
            "day_start": hhmm(minute_of(self.start)),
            "day_end": hhmm(minute_of(self.end)),
            "first_day_start": hhmm(minute_of(self.first_start)) if self.first_start else None,
            "day_hours": [
                {"start": hhmm(minute_of(start)), "end": hhmm(minute_of(end))}
                for start, end in self.each
            ],
        }


DEFAULT_HOURS = DailyHours()


def _now_min(now: datetime) -> int:
    """`now` as minutes since midnight, rounded up to the next NOW_STEP_MIN."""
    minutes = now.hour * 60 + now.minute + (now.second > 0 or now.microsecond > 0)
    return ceil(minutes / NOW_STEP_MIN) * NOW_STEP_MIN


def trip_windows(
    hours: DailyHours, city: City, first: date, days: int, now: datetime
) -> list[DayWindow]:
    """The hours of the trip's days from `first` on. A first day that is today in the city
    starts no earlier than `now`. Raises PlanningError for hours that leave no time."""
    local_now = now.astimezone(city.tz)
    point = city_point(city)
    windows: list[DayWindow] = []
    for i in range(days):
        day = first + timedelta(days=i)
        day_start, end = hours.of_day(i)
        if i == 0 and day == local_now.date():
            current = _now_min(local_now)
            if current > end - MIN_DAY_MIN:
                raise PlanningError(
                    f"It is {hhmm(current)} in {city.name}: too late for today's hours (until "
                    f"{hhmm(end)}). Start tomorrow, or end the day later."
                )
            day_start = max(day_start, current)
        if end - day_start < MIN_DAY_MIN:
            raise PlanningError(
                f"Day {i + 1} from {hhmm(day_start)} to {hhmm(end)} is too short: "
                "leave at least an hour."
            )
        if end - day_start > MINUTES_PER_DAY:
            raise PlanningError(
                f"Day {i + 1} from {hhmm(day_start)} to {hhmm(end)} the next day is longer "
                "than a day."
            )
        if windows and windows[-1].end_min - MINUTES_PER_DAY > day_start:
            raise PlanningError(
                f"Day {i} ends at {hhmm(windows[-1].end_min)} the next day, after day {i + 1} "
                f"starts at {hhmm(day_start)}."
            )
        sunrise, sunset = daylight(day, point.lat, point.lon, city.tz)
        windows.append(DayWindow(day_start, end, sunrise, sunset, on=day))
    return windows
