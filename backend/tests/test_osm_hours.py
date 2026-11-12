from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.ingest.cities import CITIES
from app.osm_hours import (
    OpenState,
    Spans,
    next_change,
    open_spans,
    open_state,
    opening_by_date,
    read_hours,
)

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


@pytest.mark.parametrize(
    ("slug", "point", "holiday"),
    [
        ("berlin", (52.5163, 13.3777), date(2026, 10, 3)),  # German Unity Day
        ("barcelona", (41.4036, 2.1744), date(2026, 10, 12)),  # Spain's National Day
        ("paris", (48.8606, 2.3376), date(2026, 7, 14)),  # Bastille Day
        ("new-york", (40.7794, -73.9632), date(2026, 7, 3)),  # Independence Day, observed
        ("tokyo", (35.7148, 139.7967), date(2026, 11, 3)),  # Culture Day
        ("sydney", (-33.8568, 151.2153), date(2026, 1, 26)),  # Australia Day
    ],
)
def test_public_holidays_of_other_countries(
    slug: str, point: tuple[float, float], holiday: date
) -> None:
    city = CITIES[slug]
    hours = read_hours("Mo-Su 10:00-18:00; PH off", city, *point)
    noon = datetime.combine(holiday, time(12), city.tz)
    assert open_state(hours, noon) == "closed"
    assert open_state(hours, noon + timedelta(days=1)) == "open"


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
    # The API's clock is in datetime.UTC, which the parser does not take as it is.
    utc = datetime(2026, 11, 2, 12, 30, tzinfo=UTC)
    assert state("Mo-Su 12:00-13:00", utc) == "open"
    hours = read_hours("Mo-Su 12:00-13:00", LISBON, *ROSSIO)
    assert next_change(hours, utc) == at(2, 13)


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


def spans(raw: str, on: date) -> Spans | None:
    hours = read_hours(raw, LISBON, *ROSSIO)
    assert hours is not None
    return open_spans(hours, on, LISBON)


H = 60
MONDAY, FRIDAY, SUNDAY = date(2026, 11, 2), date(2026, 11, 6), date(2026, 11, 8)


def test_open_spans_of_a_day_and_the_next_morning() -> None:
    museum = "Tu-Su 10:00-13:00,14:00-18:00"
    assert spans(museum, MONDAY) == ((34 * H, 37 * H), (38 * H, 42 * H))  # Tuesday's
    assert spans(museum, SUNDAY) == ((10 * H, 13 * H), (14 * H, 18 * H))  # closed Monday
    # Friday's night runs into Saturday, and on into Saturday's own hours as one span.
    market = "Mo-We 10:00-00:00; Th-Sa 10:00-02:00; Su 10:00-24:00"
    assert spans(market, FRIDAY) == ((0, 2 * H), (10 * H, 26 * H), (34 * H, 48 * H))
    assert spans("24/7", MONDAY) == ((0, 48 * H),)
    assert spans("closed", MONDAY) == ()


def test_open_spans_on_the_city_clock_in_summer() -> None:
    # Lisbon is an hour ahead of UTC in July.
    assert spans("Mo-Su 10:00-18:00", date(2026, 7, 1)) == ((10 * H, 18 * H), (34 * H, 42 * H))


def test_open_spans_of_hours_that_say_unknown() -> None:
    hours = "Mo-Fr 09:00-17:00; Sa unknown"
    assert spans(hours, MONDAY) == ((9 * H, 17 * H), (33 * H, 41 * H))
    assert spans(hours, FRIDAY) is None  # Saturday is unknown


def test_opening_by_date() -> None:
    museum = "Tu-Su 10:00-18:00; Sa unknown"
    by_date = opening_by_date(museum, LISBON, *ROSSIO, [MONDAY, SUNDAY, date(2026, 11, 7)])
    # Saturday's hours are unknown: it is left out.
    assert by_date == {MONDAY: ((34 * H, 42 * H),), SUNDAY: ((10 * H, 18 * H),)}
    assert opening_by_date(None, LISBON, *ROSSIO, [MONDAY]) is None
    assert opening_by_date("Segunda 08:00-20:00", LISBON, *ROSSIO, [MONDAY]) is None
