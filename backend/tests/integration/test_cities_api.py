"""GET /cities."""

from fastapi.testclient import TestClient


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
