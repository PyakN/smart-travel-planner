"""GET /venues: places to eat and drink around a point in the seeded town of Testville
(which keeps UTC)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_now
from app.ingest.cities import CITIES
from tests.integration.test_replace_api import TESTVILLE

PIN = {"lat": 45.0040, "lon": 7.0060}
# A Monday, at 13:00.
LUNCHTIME = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


@pytest.fixture
def venues_at(client: TestClient) -> Any:
    """Search at a given time (lunchtime unless told)."""

    def search(moment: datetime = LUNCHTIME, **params: Any) -> dict[str, Any]:
        client.app.dependency_overrides[get_now] = lambda: moment  # type: ignore[attr-defined]
        try:
            response = client.get("/venues", params={**PIN, **params})
        finally:
            client.app.dependency_overrides.pop(get_now)  # type: ignore[attr-defined]
        assert response.status_code == 200, response.text
        page: dict[str, Any] = response.json()
        return page

    return search


def names(page: dict[str, Any]) -> list[str]:
    return [v["name"] for v in page["items"]]


def test_closest_first_then_the_most_complete(venues_at: Any) -> None:
    page = venues_at()
    # A minute's walk: the café with hours, cuisine, diets, seating and a website comes
    # before the pub and the burger place, though they are closer. Sights never show.
    assert names(page) == [
        "Green Leaf Café",
        "Corner Pub",
        "Quick Burger",
        "Pizzeria Roma",
        "Veggie Garden",
        "Old Town Fado",
        "Harbour Bar",
    ]
    assert page["total"] == 7
    assert [v["walk_min"] for v in page["items"]] == [1, 1, 1, 2, 2, 7, 8]
    distances = [v["distance_m"] for v in page["items"]]
    assert 40 < distances[2] < distances[1] < distances[0] < 60

    cafe = page["items"][0]
    assert cafe == {
        "id": cafe["id"],
        "name": "Green Leaf Café",
        "category": "cafe",
        "venue_type": "cafe",
        "lat": 45.0036,
        "lon": 7.0056,
        "distance_m": cafe["distance_m"],
        "walk_min": 1,
        "cuisines": ["coffee_shop", "cake"],
        "diets": {"vegan": "yes", "vegetarian": "yes"},
        "outdoor_seating": True,
        "opening_hours": "Mo-Su 08:00-19:00",
        "open_now": "open",
        "open_on_arrival": "open",
        "changes_at": "19:00",
        "website": "https://greenleaf.example",
        "phone": None,
        "stay_min": 30,
    }
    by_name = {v["name"]: v for v in page["items"]}
    pub, burger = by_name["Corner Pub"], by_name["Quick Burger"]
    assert (pub["venue_type"], pub["open_now"], pub["changes_at"], pub["stay_min"]) == (
        "pub",
        "closed",
        "17:00",
        60,
    )
    assert (burger["venue_type"], burger["open_now"], burger["stay_min"]) == (
        "fast_food",
        "unknown",
        30,
    )
    assert by_name["Pizzeria Roma"]["outdoor_seating"] is False
    assert by_name["Veggie Garden"]["diets"] == {"vegetarian": "only"}
    assert by_name["Pizzeria Roma"]["stay_min"] == 75


def test_cuisines_in_range(venues_at: Any) -> None:
    cuisines = venues_at()["cuisines"]
    assert cuisines == [
        {"cuisine": c, "count": 1}
        for c in ["burger", "cake", "coffee_shop", "indian", "italian", "pizza", "vegetarian"]
    ]
    # Choosing one keeps the others on offer.
    pizza = venues_at(cuisine="Pizza")
    assert names(pizza) == ["Pizzeria Roma"]
    assert pizza["total"] == 1
    assert pizza["cuisines"] == cuisines


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        (
            {"kind": "food"},
            ["Green Leaf Café", "Quick Burger", "Pizzeria Roma", "Veggie Garden", "Old Town Fado"],
        ),
        ({"kind": "drinks"}, ["Corner Pub", "Harbour Bar"]),
        ({"vegetarian": True}, ["Green Leaf Café", "Veggie Garden"]),  # vegan is vegetarian
        ({"vegan": True}, ["Green Leaf Café"]),
        ({"outdoor_seating": True}, ["Green Leaf Café", "Corner Pub"]),
        # Not the pub (opens at 17:00), nor places with unknown hours.
        ({"open_now": True}, ["Green Leaf Café", "Pizzeria Roma", "Veggie Garden"]),
        (
            {"radius_m": 250, "kind": "food", "vegetarian": True},
            ["Green Leaf Café", "Veggie Garden"],
        ),
        ({"kind": "drinks", "radius_m": 250}, ["Corner Pub"]),
    ],
    ids=["food", "drinks", "vegetarian", "vegan", "outdoor", "open-now", "combined", "radius"],
)
def test_filters(venues_at: Any, params: dict[str, Any], expected: list[str]) -> None:
    assert names(venues_at(**params)) == expected


def test_far_away_places_need_a_wider_radius(venues_at: Any) -> None:
    assert "Far Café" not in names(venues_at(radius_m=2000))
    page = venues_at(radius_m=2000, limit=3)
    assert len(page["items"]) == 3
    assert page["total"] == 7


def test_open_when_you_get_there(venues_at: Any) -> None:
    # Veggie Garden closes for the afternoon at 15:00, two minutes' walk away.
    page = venues_at(datetime(2026, 11, 2, 14, 59, tzinfo=UTC), kind="food")
    garden = next(v for v in page["items"] if v["name"] == "Veggie Garden")
    assert (garden["open_now"], garden["open_on_arrival"], garden["changes_at"]) == (
        "open",
        "closed",
        "15:00",
    )
    open_then = venues_at(datetime(2026, 11, 2, 14, 59, tzinfo=UTC), open_now=True)
    assert "Veggie Garden" not in names(open_then)


@pytest.mark.parametrize(
    "params",
    [
        {"radius_m": 100},
        {"radius_m": 5000},
        {"kind": "coffee"},
        {"limit": 0},
        {"lat": 95},
    ],
)
def test_invalid_searches(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/venues", params={**PIN, **params}).status_code == 422


def test_a_point_is_needed(client: TestClient) -> None:
    assert client.get("/venues", params={"lat": PIN["lat"]}).status_code == 422
