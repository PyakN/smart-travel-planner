"""GET /cities, and POST /plan for the city the traveller chose."""

import pytest
from fastapi.testclient import TestClient

from app.ingest.cities import CITIES
from app.schemas.trip import PlaceSelection
from tests.fakes import FakeProvider
from tests.integration.test_replace_api import FIRST_DAY, TESTVILLE
from tests.test_trip_schema import trip


def test_lists_the_supported_cities(client: TestClient) -> None:
    response = client.get("/cities")
    assert response.status_code == 200
    cities = {city["slug"]: city for city in response.json()}
    assert list(cities) == ["lisbon", "berlin", "barcelona"]
    assert cities["berlin"] == {
        "slug": "berlin",
        "name": "Berlin",
        "timezone": "Europe/Berlin",
        "bbox": [13.0883, 52.3382, 13.7612, 52.6756],
    }
    assert cities["barcelona"]["timezone"] == "Europe/Madrid"


def test_plans_the_chosen_city_when_the_text_names_none(
    client: TestClient,
    llm: FakeProvider,
    place_ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)
    llm.queue(
        trip(city=None, days=1, pace="relaxed"),
        PlaceSelection(place_ids=[place_ids[n] for n in FIRST_DAY], rationale="Test."),
    )
    response = client.post("/plan", json={"text": "A slow day of sights", "city": "testville"})
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["city"] == "testville"
    assert {stop["name"] for stop in plan["days"][0]["stops"]} == set(FIRST_DAY)


def test_refuses_a_text_about_another_city_than_the_chosen_one(
    client: TestClient, llm: FakeProvider
) -> None:
    llm.queue(trip(city="lisbon"))
    response = client.post("/plan", json={"text": "A day in Lisbon", "city": "berlin"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Your request is for Lisbon, but Berlin is chosen."


def test_refuses_an_unknown_city(client: TestClient, llm: FakeProvider) -> None:
    response = client.post("/plan", json={"text": "A day in Tokyo", "city": "tokyo"})
    assert response.status_code == 422
    assert "unknown city; supported: lisbon, berlin, barcelona" in response.text
    assert llm.calls == []
