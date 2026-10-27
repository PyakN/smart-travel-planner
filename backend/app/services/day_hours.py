"""The hours of a trip's days: the traveller's daily hours, a first day that starts later
(today: from now on), and every day's daylight.

Times are the city's wall clock in minutes since midnight of each trip day, as in the
optimizer; a day that ends after midnight ends past 24 * 60.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil

from app.ingest.cities import City
from app.optimizer.planner import MINUTES_PER_DAY, DayWindow
from app.services.place_selection import PlanningError
from app.services.weather_service import city_point
from app.sun import daylight

# A day needs this long for one visit and the way there.
MIN_DAY_MIN = 60
# A trip that starts today starts at the next quarter of an hour.
NOW_STEP_MIN = 15


def clock(minute: int) -> str:
    """Minutes since midnight as HH:MM, the next morning's too."""
    minute %= MINUTES_PER_DAY
    return f"{minute // 60:02d}:{minute % 60:02d}"


def minute_of(moment: time) -> int:
    return moment.hour * 60 + moment.minute


@dataclass(frozen=True)
class DailyHours:
    """The traveller's hours: every day from `start` to `end` (the next morning when `end`
    is not after `start`), and the first day from `first_start` if that is given."""

    start: time = time(9, 30)
    end: time = time(21, 30)
    first_start: time | None = None

    def as_params(self) -> dict[str, str | None]:
        return {
            "day_start": clock(minute_of(self.start)),
            "day_end": clock(minute_of(self.end)),
            "first_day_start": clock(minute_of(self.first_start)) if self.first_start else None,
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
    start, end = minute_of(hours.start), minute_of(hours.end)
    if end <= start:
        end += MINUTES_PER_DAY
    local_now = now.astimezone(city.tz)
    point = city_point(city)
    windows = []
    for i in range(days):
        day = first + timedelta(days=i)
        day_start = start
        if i == 0 and hours.first_start is not None:
            day_start = minute_of(hours.first_start)
        if i == 0 and day == local_now.date():
            current = _now_min(local_now)
            if current > end - MIN_DAY_MIN:
                raise PlanningError(
                    f"It is {clock(current)} in {city.name}: too late for today's hours (until "
                    f"{clock(end)}). Start tomorrow, or end the day later."
                )
            day_start = max(day_start, current)
        if end - day_start < MIN_DAY_MIN:
            raise PlanningError(
                f"Day {i + 1} from {clock(day_start)} to {clock(end)} is too short: "
                "leave at least an hour."
            )
        if end - day_start > MINUTES_PER_DAY:
            raise PlanningError(
                f"Day {i + 1} from {clock(day_start)} to {clock(end)} the next day is longer "
                "than a day."
            )
        sunrise, sunset = daylight(day, point.lat, point.lon, city.tz)
        windows.append(DayWindow(day_start, end, sunrise, sunset))
    return windows
