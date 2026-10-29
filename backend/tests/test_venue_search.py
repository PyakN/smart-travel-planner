from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.repositories.places import Near, NearbyPlace
from app.schemas.venue import VenueOut
from app.services.venue_search import (
    VenueFilters,
    describe_venue,
    normalize_cuisine,
    venue_page,
    walk_minutes,
)

# Thursday 29 October 2026, 13:00 in Lisbon (UTC+0 in winter).
NOW = datetime(2026, 10, 29, 13, 0, tzinfo=UTC)


def place(category: str = "restaurant", distance_m: float = 100.0, **tags: str) -> NearbyPlace:
    return NearbyPlace(
        id=1,
        name="Tasca",
        city="lisbon",
        category=category,
        lat=38.7139,
        lon=-9.1394,
        tags=tags,
        website=None,
        opening_hours=tags.get("opening_hours"),
        distance_m=distance_m,
    )


def venue(**tags: str) -> VenueOut:
    return describe_venue(place(**tags), NOW)


@pytest.mark.parametrize(
    ("category", "tags", "venue_type", "stay_min"),
    [
        ("restaurant", {"amenity": "restaurant"}, "restaurant", 75),
        ("restaurant", {"amenity": "fast_food"}, "fast_food", 30),
        ("cafe", {"amenity": "cafe"}, "cafe", 30),
        ("cafe", {"amenity": "ice_cream"}, "ice_cream", 15),
        ("cafe", {"shop": "pastry", "tourism": "attraction"}, "pastry", 30),
        ("nightlife", {"amenity": "bar"}, "bar", 60),
        ("nightlife", {"amenity": "nightclub"}, "nightclub", 120),
        # Tags that say no more than the category.
        ("nightlife", {}, "bar", 60),
        ("cafe", {"amenity": "restaurant;cafe"}, "cafe", 30),
    ],
)
def test_venue_types_and_stays(
    category: str, tags: dict[str, str], venue_type: str, stay_min: int
) -> None:
    described = describe_venue(place(category, **tags), NOW)
    assert (described.venue_type, described.stay_min) == (venue_type, stay_min)


def test_cuisines() -> None:
    assert venue(cuisine="Portuguese; coffee shop;;portuguese").cuisines == [
        "portuguese",
        "coffee_shop",
    ]
    assert venue().cuisines == []
    assert normalize_cuisine("  Coffee   Shop ") == "coffee_shop"


@pytest.mark.parametrize(
    ("tags", "diets"),
    [
        ({"diet:vegetarian": "yes"}, {"vegetarian": "yes"}),
        ({"diet:vegetarian": "no", "diet:halal": "limited"}, {}),
        ({"diet:vegan": "only"}, {"vegan": "only", "vegetarian": "only"}),
        ({"diet:vegan": "yes"}, {"vegan": "yes", "vegetarian": "yes"}),
        ({"diet:vegetarian": "only", "diet:vegan": "yes"}, {"vegetarian": "only", "vegan": "yes"}),
        ({"cuisine": "vegetarian;indian"}, {"vegetarian": "only"}),
        ({"cuisine": "vegan"}, {"vegan": "only", "vegetarian": "only"}),
        ({"diet:gluten_free": "yes"}, {"gluten_free": "yes"}),
    ],
)
def test_diets(tags: dict[str, str], diets: dict[str, str]) -> None:
    assert venue(**tags).diets == diets


def test_outdoor_seating() -> None:
    assert venue(outdoor_seating="yes").outdoor_seating is True
    assert venue(outdoor_seating="no").outdoor_seating is False
    assert venue(outdoor_seating="pedestrian_zone").outdoor_seating is None
    assert venue().outdoor_seating is None


def test_opening_and_closing_within_a_day() -> None:
    lunch = venue(opening_hours="Mo-Su 12:00-15:00,19:00-23:00")
    assert (lunch.open_now, lunch.changes_at) == ("open", "15:00")
    # Closed until next Monday: too far ahead for a clock time.
    monday = venue(opening_hours="Mo 12:00-15:00")
    assert (monday.open_now, monday.changes_at) == ("closed", None)
    unread = venue(opening_hours="Segunda a sexta 12:00-15:00")
    assert (unread.open_now, unread.open_on_arrival, unread.changes_at) == (
        "unknown",
        "unknown",
        None,
    )
    assert unread.opening_hours == "Segunda a sexta 12:00-15:00"  # shown as mapped


def test_unknown_cities_have_unknown_hours() -> None:
    elsewhere = describe_venue(replace(place(opening_hours="24/7"), city="atlantis"), NOW)
    assert elsewhere.open_now == "unknown"


@pytest.mark.parametrize(("distance_m", "minutes"), [(0, 1), (40, 1), (100, 2), (500, 10)])
def test_walk_minutes(distance_m: float, minutes: int) -> None:
    # 4 km/h along streets 1.3 times longer than the straight line.
    assert walk_minutes(distance_m) == minutes


def test_page_orders_by_minute_then_data_then_distance() -> None:
    near = Near(38.7139, -9.1394, 500)
    bare = describe_venue(place(distance_m=10), NOW)
    rich = describe_venue(
        place(distance_m=60, cuisine="pizza", opening_hours="24/7", phone="+351 21"), NOW
    )
    farther = describe_venue(place(distance_m=200, cuisine="sushi"), NOW)
    page = venue_page([farther, bare, rich], VenueFilters(near=near, limit=2))
    assert [v.distance_m for v in page.items] == [60, 10]
    assert page.total == 3
    assert [(c.cuisine, c.count) for c in page.cuisines] == [("pizza", 1), ("sushi", 1)]
