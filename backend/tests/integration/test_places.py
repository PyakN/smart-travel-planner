from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.catalog import CATEGORY_SLUGS

PRACA_DO_COMERCIO = {"lat": 38.7075, "lon": -9.1364}


def names(page: dict[str, Any]) -> list[str]:
    return [item["name"] for item in page["items"]]


def search(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/places", params=params)
    assert response.status_code == 200, response.text
    page: dict[str, Any] = response.json()
    return page


def test_city_filter_puts_wikidata_places_first(client: TestClient) -> None:
    page = search(client, city="lisbon")
    assert page["total"] == 5
    assert names(page) == [
        "Castelo de São Jorge",
        "Praça do Comércio",
        "Torre de Belém",
        "Miradouro de Santa Luzia",
        "Museu Calouste Gulbenkian",
    ]
    assert all(item["distance_m"] is None for item in page["items"])


def test_multiple_categories(client: TestClient) -> None:
    page = search(client, city="lisbon", category=["museum", "viewpoint"])
    assert sorted(names(page)) == ["Miradouro de Santa Luzia", "Museu Calouste Gulbenkian"]


def test_radius_search_is_sorted_by_distance(client: TestClient) -> None:
    page = search(client, **PRACA_DO_COMERCIO, radius_m=800)
    assert names(page) == ["Praça do Comércio", "Miradouro de Santa Luzia", "Castelo de São Jorge"]
    distances = [item["distance_m"] for item in page["items"]]
    assert distances[0] == pytest.approx(0, abs=0.01)
    assert distances == sorted(distances)
    assert 650 < distances[1] < 800


def test_bbox_search(client: TestClient) -> None:
    belem = "-9.23,38.68,-9.20,38.70"
    assert names(search(client, bbox=belem)) == ["Torre de Belém"]


def test_coordinates_round_trip(client: TestClient) -> None:
    [place] = search(client, city="lisbon", category="viewpoint")["items"]
    assert (place["lat"], place["lon"]) == pytest.approx((38.7116, -9.1301))


def test_pagination(client: TestClient) -> None:
    first = search(client, city="lisbon", limit=2, offset=0)
    second = search(client, city="lisbon", limit=2, offset=2)
    assert first["total"] == second["total"] == 5
    assert len(first["items"]) == len(second["items"]) == 2
    assert not set(names(first)) & set(names(second))


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("sao jorge", ["Castelo de São Jorge"]),  # accents ignored
        ("BELEM TOWER", ["Torre de Belém"]),  # English name
        ("100%", []),  # wildcards are literal
    ],
)
def test_name_search(client: TestClient, q: str, expected: list[str]) -> None:
    assert names(search(client, city="lisbon", q=q)) == expected


@pytest.mark.parametrize("q", ["Kinkaku", "金閣寺"])
def test_name_search_finds_names_in_another_script(client: TestClient, q: str) -> None:
    assert names(search(client, city="kyoto", q=q)) == ["Kinkaku-ji"]


def test_name_search_puts_prefix_matches_first(client: TestClient) -> None:
    # Without the prefix rule the City Museum (with Wikidata) would come first.
    assert names(search(client, q="museum", city="testville")) == ["Museum of Toys", "City Museum"]


@pytest.mark.parametrize(
    "params",
    [
        {"q": "a"},  # too short
        {"lat": 38.7, "lon": -9.1},  # radius missing
        {"radius_m": 500},  # point missing
        {**PRACA_DO_COMERCIO, "radius_m": 50_000},  # radius too large
        {"bbox": "1,2,3"},
        {"bbox": "-9.1,38.7,-9.2,38.8"},  # west > east
        {"limit": 1000},
    ],
)
def test_invalid_params(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/places", params=params).status_code == 422


def test_get_place(client: TestClient, place_ids: dict[str, int]) -> None:
    place_id = place_ids["Torre de Belém"]
    response = client.get(f"/places/{place_id}")
    assert response.status_code == 200
    assert response.json()["category"] == "landmark"


def test_get_missing_place(client: TestClient) -> None:
    assert client.get("/places/999999").status_code == 404


def test_categories_with_counts(client: TestClient) -> None:
    response = client.get("/categories", params={"city": "lisbon"})
    counts = {c["slug"]: c["place_count"] for c in response.json()}
    assert counts["landmark"] == 3
    assert counts["museum"] == 1  # Serralves is in Porto
    assert counts["market"] == 0
    assert tuple(counts) == CATEGORY_SLUGS  # every category, even without places
