"""Choosing places for the days' hours: how many go before and after 20:00, and in daylight."""

from app.catalog import VisitHours
from app.optimizer.planner import DayWindow
from app.repositories.candidates import Candidate
from app.services.place_selection import (
    DaySlots,
    day_slots,
    describe_hours,
    evening_warnings,
    fit_hours,
    is_timed,
    limit_outdoor,
    merge_ranked,
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
    slots = day_slots(OVERNIGHT, "moderate")
    assert (slots.places, slots.night, slots.before_night, slots.outdoor) == (6, 3, 3, 1)
    assert slots.busy == ((16 * H, 20 * H), (20 * H, 23 * H + 20))
    assert describe_hours(OVERNIGHT, slots) == (
        "16:00-03:00, dark from 17:41: 3 before 20:00 (at most 1 outdoors), 3 from 20:00"
    )


def test_a_night_out_is_all_evening() -> None:
    night = DayWindow(21 * H, 27 * H, 7 * H, SUNSET)
    slots = day_slots(night, "relaxed")
    assert (slots.places, slots.night, slots.outdoor) == (2, 2, 0)
    assert describe_hours(night, slots) == "21:00-03:00: 2 from 20:00"


class TestFitHours:
    SLOTS = [day_slots(OVERNIGHT, "moderate")]  # 3 before 20:00, at most 1 outdoors; 3 after
    POOL = [place(i, "day") for i in (10, 11)] + [place(i, "night") for i in (12, 13, 14)]

    def test_picks_that_fit_stay(self) -> None:
        picks = [place(1, "daylight"), place(2, "day"), place(3, "day")] + self.POOL[2:]
        places, swaps = fit_hours(picks, picks + self.POOL, self.SLOTS)
        assert (ids(places), swaps) == (ids(picks), [])

    def test_outdoor_sights_beyond_daylight_go_indoors(self) -> None:
        picks = [place(i, "daylight") for i in (1, 2, 3)] + self.POOL[2:]
        places, swaps = fit_hours(picks, picks + self.POOL, self.SLOTS)
        assert ids(places) == [1, 11, 10, 12, 13, 14]  # the least important ones went
        assert [(a.id, b.id) for a, b, _ in swaps] == [(3, 10), (2, 11)]
        assert swaps[0][2] == "Your hours leave too little daylight for it."

    def test_evenings_get_places_open_at_night(self) -> None:
        picks = [place(i, "day") for i in (1, 2, 3, 4, 5)] + [place(6, "night")]
        # Ranked: a lit square first, then the bars.
        pool = picks + [place(7, "any", score=0.5), *self.POOL[2:]]
        places, swaps = fit_hours(picks, pool, self.SLOTS)
        assert ids(places) == [1, 2, 3, 12, 7, 6]
        assert all(p.hours in ("night", "any") for p in places[3:])
        assert {reason for *_, reason in swaps} == {
            "It closes at 20:00, and more of your day is in the evening."
        }

    def test_afternoons_get_places_open_by_day(self) -> None:
        # Seen live: five fado houses and a museum for an afternoon and an evening of three.
        fado = [place(i, "night", category="restaurant") for i in (1, 2, 3, 4, 5)]
        picks = [*fado, place(6, "day")]
        pool = [*picks, place(7, "day"), place(8, "any"), place(9, "night"), place(10, "night")]
        places, swaps = fit_hours(picks, pool, self.SLOTS)
        assert sum(p.category == "restaurant" for p in places) == 1  # one dinner
        assert sum(p.hours == "night" for p in places) == 3
        assert sum(p.hours in ("day", "daylight") for p in places) <= 3
        assert {p.id for p in places} >= {1, 6, 9, 10}  # the best fado house stays
        assert {reason for *_, reason in swaps} == {
            "One dinner an evening is enough: a bar or a square instead.",
            "It opens at 20:00, and your hours have more time before then.",
        }

    def test_a_place_swapped_out_does_not_come_back(self) -> None:
        dinners = [place(i, "night", category="restaurant") for i in (1, 2, 3)]
        bar, other_bar, square = place(4, "night"), place(8, "night"), place(9, "any")
        picks = [*dinners, bar, place(5, "day"), place(6, "day")]
        pool = [*picks, place(7, "day"), other_bar, square]
        places, swaps = fit_hours(picks, pool, self.SLOTS)
        # The bar made way for the afternoon; the dinners after it take the other places.
        assert bar not in places
        assert ids(places) == [1, 9, 8, 7, 5, 6]
        assert [old.id for old, _, _ in swaps] == [4, 3, 2]

    def test_must_visit_places_count_but_stay(self) -> None:
        must = [place(1, "daylight")]
        picks = [place(2, "daylight"), place(3, "day")]
        places, swaps = fit_hours(picks, must + picks + self.POOL, self.SLOTS, must)
        assert ids(places) == [10, 3]  # the daylight slot is the must-visit place's
        assert [(a.id, b.id) for a, b, _ in swaps] == [(2, 10)]


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


def test_evening_interests_on_a_day_without_evening() -> None:
    bars = trip(interests=["nightlife", "viewpoint"])
    assert evening_warnings(bars, [day_slots(DEFAULT, "moderate")]) == [
        "Bars, fado houses and restaurants open at 20:00: end the day later to visit them."
    ]
    assert evening_warnings(bars, [day_slots(OVERNIGHT, "moderate")]) == []
    assert evening_warnings(trip(interests=["viewpoint"]), [day_slots(DEFAULT, "moderate")]) == []
