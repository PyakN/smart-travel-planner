from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.ingest.cities import CITIES
from app.osm_hours import OpenState, next_change, open_state, read_hours

LISBON = CITIES["lisbon"]
ROSSIO = (38.7139, -9.1394)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in Lisbon in November 2026 (the 2nd is a Monday)."""
    return datetime(2026, 11, day, hour, minute, tzinfo=LISBON.tz)


def state(raw: str | None, moment: datetime) -> OpenState:
    return open_state(read_hours(raw, LISBON, *ROSSIO), moment)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (at(2, 11, 59), "closed"),
        (at(2, 12), "open"),
        (at(2, 16), "closed"),  # between lunch and dinner
        (at(2, 22, 59), "open"),
        (at(7, 1, 30), "open"),  # Friday's hours run past midnight
        (at(7, 13), "closed"),  # Saturdays closed
        (at(8, 13), "closed"),  # Sundays off
    ],
)
def test_restaurant_hours(moment: datetime, expected: OpenState) -> None:
    hours = "Mo-Th 12:00-15:00,19:00-23:00; Fr 12:00-15:00,19:00-02:00; Su off"
    assert state(hours, moment) == expected


def test_a_later_rule_takes_the_whole_day() -> None:
    # As in OSM's spec: Saturday's own hours replace the night that ran over from Friday.
    hours = "Fr 19:00-02:00; Sa 19:00-23:00"
    assert state(hours, at(7, 1, 30)) == "closed"


def test_public_holidays_of_the_city() -> None:
    # 1 December, Restoration of Independence: a public holiday in Portugal.
    hours = "Mo-Su 10:00-18:00; PH off"
    assert state(hours, datetime(2026, 12, 1, 12, 0, tzinfo=LISBON.tz)) == "closed"
    assert state(hours, datetime(2026, 12, 2, 12, 0, tzinfo=LISBON.tz)) == "open"


def test_daylight_hours_follow_the_sun() -> None:
    # Lisbon's sunset on 2 November 2026 is at about 17:25.
    assert state("sunrise-sunset", at(2, 17, 15)) == "open"
    assert state("sunrise-sunset", at(2, 17, 40)) == "closed"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "  ",
        "Segunda 08:00-20:00 Terça 08:00-20:00 Domingo Fechado",  # not the OSM syntax
        "Mo-Su 12:00-15:00 19:00-22:30",
    ],
)
def test_hours_that_cannot_be_read_are_unknown(raw: str | None) -> None:
    assert read_hours(raw, LISBON, *ROSSIO) is None
    assert state(raw, at(7, 12)) == "unknown"
    assert next_change(None, at(7, 12)) is None


def test_hours_can_say_unknown() -> None:
    hours = read_hours("Mo-Fr 09:00-17:00; Sa unknown", LISBON, *ROSSIO)
    assert open_state(hours, at(7, 12)) == "unknown"  # a Saturday
    assert next_change(hours, at(7, 12)) == at(8, 0)  # closed on Sundays


def test_moments_in_other_time_zones() -> None:
    # 13:30 in Paris is 12:30 in Lisbon (both on winter time).
    paris = datetime(2026, 11, 2, 13, 30, tzinfo=ZoneInfo("Europe/Paris"))
    assert state("Mo-Su 12:00-13:00", paris) == "open"


def test_next_change_in_the_city_time() -> None:
    hours = read_hours("Mo-Fr 12:00-15:00,19:00-23:00", LISBON, *ROSSIO)
    assert next_change(hours, at(2, 13)) == at(2, 15)
    assert next_change(hours, at(2, 16)) == at(2, 19)
    assert next_change(hours, at(6, 23, 30)) == at(9, 12)  # Friday night: Monday at noon
    changed = next_change(hours, at(2, 13))
    assert changed is not None and changed.utcoffset() == LISBON.tz.utcoffset(at(2, 13))


def test_no_change_ahead() -> None:
    assert next_change(read_hours("24/7", LISBON, *ROSSIO), at(2, 12)) is None
    # Closed until spring: farther than the lookahead.
    seasonal = read_hours("Apr-Sep Mo-Su 10:00-19:00", LISBON, *ROSSIO)
    assert open_state(seasonal, at(2, 12)) == "closed"
    assert next_change(seasonal, at(2, 12)) is None
