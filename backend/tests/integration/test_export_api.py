"""GET /plans/{id}/gpx: a saved plan as a GPX file, in the seeded town of Testville."""

from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.ingest.cities import CITIES
from tests.fakes import FakeProvider
from tests.integration.test_replace_api import FIRST_DAY, TESTVILLE, create_plan, names
from tests.test_gpx_export import NS, texts


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


def test_plan_as_gpx(client: TestClient, llm: FakeProvider, place_ids: dict[str, int]) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY, start_date="2026-11-03")

    response = client.get(f"/plans/{plan['id']}/gpx")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/gpx+xml"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="testville-plan-{plan["id"]}.gpx"'
    )
    root = ET.fromstring(response.content)
    assert texts(root, "gpx:wpt/gpx:name") == [
        f"{n}. {name}" for n, name in enumerate(names(plan), 1)
    ]
    first = plan["days"][0]["stops"][0]
    assert texts(root, "gpx:wpt/gpx:time")[0] == f"2026-11-03T{first['arrive']}:00Z"
    points = root.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)
    assert len(points) == sum(len(s["geometry"]) for s in plan["days"][0]["segments"])


def test_one_day_of_a_plan(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, [*FIRST_DAY, "City Museum", "Far Fort"], days=2)
    assert len(plan["days"]) == 2

    response = client.get(f"/plans/{plan['id']}/gpx", params={"day": 2})
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].endswith(f'-plan-{plan["id"]}-day-2.gpx"')
    root = ET.fromstring(response.content)
    assert texts(root, "gpx:trk/gpx:name") == ["Day 2"]
    assert len(root.findall("gpx:wpt", NS)) == len(plan["days"][1]["stops"])


def test_unknown_plan_or_day(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    plan = create_plan(client, llm, place_ids, FIRST_DAY)
    assert client.get("/plans/999999/gpx").status_code == 404
    response = client.get(f"/plans/{plan['id']}/gpx", params={"day": 2})
    assert response.status_code == 404
    assert response.json()["detail"] == "Day 2 is not in this plan."
    assert client.get(f"/plans/{plan['id']}/gpx", params={"day": 0}).status_code == 422
