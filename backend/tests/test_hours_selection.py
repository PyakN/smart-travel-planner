"""Choosing places for the days' hours: how many go before and after 20:00, and in daylight."""

from app.catalog import VisitHours
from app.optimizer.planner import DayWindow
from app.repositories.candidates import Candidate
from app.services.place_selection import (
    VENUE_NOTE,
    DaySlots,
    day_slots,
    describe_hours,
    fit_hours,
    is_timed,
    limit_outdoor,
    merge_ranked,
    venue_notes,
)
from tests.test_trip_schema import trip

H = 60
SUNSET = 17 * H + 41
DEFAULT = DayWindow(sunrise_min=7 * H, sunset_min=SUNSET)
AFTERNOON = DayWindow(16 * H, 21 * H + 30, 7 * H, SUNSET)
OVERNIGHT = DayWindow(16 * H, 27 * H, 7 * H, SUNSET)

CATEGORY: dict[VisitHours, str] = {
    "day": "museum",
    "daylight": "viewpoint",
    "night": "nightlife",
    "any": "landmark",
}


def place(
    i: int, hours: VisitHours, score: float | None = None, category: str | None = None
) -> Candidate:
    return Candidate(
        i,
        f"Place {i}",
        category or CATEGORY[hours],
        10 - i if score is None else score,
        None,
        38.7,
        -9.1,
        outdoor=hours == "daylight",
        hours=hours,
    )


def ids(places: list[Candidate]) -> list[int]:
    return [p.id for p in places]


def test_a_default_day_has_no_evening() -> None:
    assert day_slots(DEFAULT, "moderate") == DaySlots(6, 0, 6, ((9 * H + 30, 17 * H + 30),))
    assert not is_timed([day_slots(DEFAULT, "moderate")])
    # An intense day runs past sunset: fewer outdoor places than places.
    intense = day_slots(DEFAULT, "intense")
    assert (intense.places, intense.night, intense.outdoor) == (8, 0, 7)
    assert is_timed([intense])


def test_an_afternoon_holds_three_places() -> None:
    slots = day_slots(AFTERNOON, "moderate")
    assert (slots.places, slots.night, slots.outdoor) == (3, 0, 1)
    assert slots.busy == ((16 * H, 19 * H + 40),)


def test_a_day_until_three_in_the_morning() -> None:
    # The evening holds 2 places, not the 3 its share of the pace would: the rest is free.
    slots = day_slots(OVERNIGHT, "moderate")
    assert (slots.places, slots.night, slots.before_night, slots.outdoor) == (5, 2, 3, 1)
    assert slots.busy == ((16 * H, 20 * H), (20 * H, 22 * H + 13))
    assert describe_hours(OVERNIGHT, slots) == (
        "16:00-03:00, dark from 17:41: 3 before 20:00 (at most 1 outdoors), 2 from 20:00"
    )


def test_a_night_out_is_all_evening() -> None:
    night = DayWindow(21 * H, 27 * H, 7 * H, SUNSET)
    slots = day_slots(night, "relaxed")
    assert (slots.places, slots.night, slots.outdoor) == (2, 2, 0)
    assert describe_hours(night, slots) == "21:00-03:00: 2 from 20:00"
    # A few places, however intense the pace.
    intense = day_slots(DayWindow(20 * H, 27 * H, 7 * H, SUNSET), "intense")
    assert (intense.places, intense.night) == (2, 2)
    assert intense.busy == ((20 * H, 22 * H + 20),)


class TestFitHours:
    SLOTS = [day_slots(OVERNIGHT, "moderate")]  # 3 before 20:00, at most 1 outdoors; 2 after
    POOL = [place(i, "day") for i in (10, 11)] + [place(i, "any") for i in (12, 13)]

    def test_picks_that_fit_stay(self) -> None:
        picks = [place(1, "daylight"), place(2, "day"), place(3, "day")] + self.POOL[2:]
        places, swaps = fit_hours(picks, picks + self.POOL, self.SLOTS)
        assert (ids(places), swaps) == (ids(picks), [])

    def test_outdoor_sights_beyond_daylight_go_indoors(self) -> None:
        picks = [place(i, "daylight") for i in (1, 2, 3)] + self.POOL[2:]
        places, swaps = fit_hours(picks, picks + self.POOL, self.SLOTS)
        assert ids(places) == [1, 11, 10, 12, 13]  # the least important ones went
        assert [(a.id, b.id) for a, b, _ in swaps] == [(3, 10), (2, 11)]
        assert swaps[0][2] == "Your hours leave too little daylight for it."

    def test_evenings_get_places_open_at_night(self) -> None:
        picks = [place(i, "day") for i in (1, 2, 3, 4, 5)]
        # Ranked: a lit square first, then the other places open at night.
        pool = picks + [place(7, "any", score=0.5), *self.POOL[2:]]
        places, swaps = fit_hours(picks, pool, self.SLOTS)
        assert ids(places) == [1, 2, 3, 12, 7]
        assert all(p.hours == "any" for p in places[3:])
        assert {reason for *_, reason in swaps} == {
            "It closes at 20:00, and more of your day is in the evening."
        }

    def test_the_evening_pool_is_for_the_evening(self) -> None:
        # Seen live: four squares from the evening's pool, and one museum for the afternoon.
        squares = [place(i, "any") for i in (20, 21, 22, 23)]
        picks = [place(1, "day"), *squares]
        evening = {s.id for s in squares}
        places, swaps = fit_hours(picks, picks + self.POOL, self.SLOTS, evening_pool=evening)
        assert ids(places) == [1, 20, 21, 11, 10]  # the least important squares went
        assert [(a.id, b.id) for a, b, _ in swaps] == [(23, 10), (22, 11)]
        assert swaps[0][2] == "Your evening has its places already: a sight for the day instead."
        # With no sight for the day left (a viewpoint has no daylight for it), they stay.
        viewpoints = [place(30, "daylight"), place(31, "daylight")]
        places, swaps = fit_hours(picks, picks + viewpoints, self.SLOTS, evening_pool=evening)
        assert (ids(places), swaps) == (ids(picks), [])

    def test_no_swap_undoes_another(self) -> None:
        # Seen live: a square made way for an outdoor sight, which then made way for another
        # square, as the daylight was taken. Now the daylight goes first, and to a museum.
        picks = [place(i, "daylight") for i in (1, 2)] + [place(i, "any") for i in (20, 21, 22)]
        pool = [*picks, place(30, "daylight"), *self.POOL, place(23, "any")]
        places, swaps = fit_hours(picks, pool, self.SLOTS, evening_pool={20, 21, 22, 23})
        assert ids(places) == [1, 10, 20, 21, 11]
        assert [(a.id, b.id) for a, b, _ in swaps] == [(2, 10), (22, 11)]

    def test_must_visit_places_count_but_stay(self) -> None:
        must = [place(1, "daylight")]
        picks = [place(2, "daylight"), place(3, "day")]
        places, swaps = fit_hours(picks, must + picks + self.POOL, self.SLOTS, must)
        assert ids(places) == [10, 3]  # the daylight slot is the must-visit place's
        assert [(a.id, b.id) for a, b, _ in swaps] == [(2, 10)]

    def test_a_must_visit_bar_takes_an_evening_place(self) -> None:
        bar = [place(1, "night")]
        picks = [place(i, "day") for i in (2, 3, 4, 5)]
        places, swaps = fit_hours(picks, bar + picks + self.POOL, self.SLOTS, bar)
        assert ids(places) == [2, 3, 4, 12]  # the other evening place is a sight open then
        assert [(a.id, b.id) for a, b, _ in swaps] == [(5, 12)]


def test_rain_swaps_keep_the_time_of_day() -> None:
    # An outdoor sight in the rain makes way for a museum, never for a bar that opens at 20:00.
    picks = [place(1, "daylight"), place(2, "daylight")]
    pool = [*picks, place(3, "night"), place(4, "day")]
    places, swaps = limit_outdoor(picks, pool, limit=1)
    assert ids(places) == [1, 4]
    assert [(a.id, b.id) for a, b in swaps] == [(2, 4)]


def test_pools_merge_into_one_ranking() -> None:
    a, b, c = place(1, "day", score=3.0), place(2, "night", score=5.0), place(3, "any", score=1.0)
    assert ids(merge_ranked([a, c], [b, a])) == [2, 1, 3]


def test_food_and_drink_requests_get_a_note() -> None:
    assert venue_notes(trip(interests=["nightlife", "viewpoint"])) == [VENUE_NOTE]
    assert venue_notes(trip(interests=["restaurant"])) == [VENUE_NOTE]
    assert venue_notes(trip(interests=["cafe"])) == [VENUE_NOTE]
    assert "find places to eat and drink" in VENUE_NOTE
    assert venue_notes(trip(interests=["viewpoint"], avoid=["nightlife"])) == []
