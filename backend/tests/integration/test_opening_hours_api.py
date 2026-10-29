"""Places keep their own OSM opening hours on the trip's dates, in the seeded town of
Testville (which keeps UTC). The Museum of Toys opens Tuesday to Sunday, 10:00 to 18:00."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.ingest.cities import CITIES
from tests.fakes import FakeProvider
from tests.integration.test_day_edit_api import at, drafted, saved_trip, stops
from tests.integration.test_replace_api import (
    TESTVILLE,
    candidate_ids,
    create_plan,
    picks,
    replace,
)

MONDAY, TUESDAY = "2026-11-02", "2026-11-03"
AFTERNOON = {"day_start": "16:00", "day_end": "21:30"}


@pytest.fixture(autouse=True)
def testville(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CITIES, "testville", TESTVILLE)


def offered(llm: FakeProvider) -> set[int]:
    """Ids of the candidates offered in the last selection prompt."""
    lines = str(llm.calls[-1]["prompt"]).split("Candidates (", 1)[1].splitlines()[1:]
    return {int(line.split(" | ", 1)[0]) for line in lines if " | " in line}


def test_places_closed_on_every_day_of_the_trip_are_not_offered(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    toys = place_ids["Museum of Toys"]
    create_plan(client, llm, place_ids, ["City Museum"], start_date=MONDAY)
    assert toys not in offered(llm)
    create_plan(client, llm, place_ids, ["City Museum"], start_date=TUESDAY)
    assert toys in offered(llm)
    # One open day of the trip is enough.
    create_plan(client, llm, place_ids, ["City Museum"], days=2, start_date=MONDAY)
    assert toys in offered(llm)


def test_a_museum_is_visited_before_it_closes(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    # The town's sights close at 20:00 when their hours are unknown; this one at 18:00, so
    # its 90-minute visit goes first, before the more important cathedral's 25 minutes.
    plan = create_plan(
        client,
        llm,
        place_ids,
        ["Testville Cathedral", "Museum of Toys"],
        start_date=TUESDAY,
        **AFTERNOON,
    )
    assert plan["dropped"] == []
    museum, cathedral = stops(plan)
    assert (museum["name"], museum["arrive"], museum["leave"]) == (
        "Museum of Toys",
        "16:00",
        "17:30",
    )
    assert cathedral["leave"] <= "20:00"


def test_replacements_open_on_the_days_date(
    client: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    toys = place_ids["Museum of Toys"]
    for date, open_then in ((MONDAY, False), (TUESDAY, True)):
        plan = create_plan(client, llm, place_ids, ["City Museum", "Clock Tower"], start_date=date)
        picks(llm, place_ids["River Park"])
        assert replace(client, plan, 1, [place_ids["Clock Tower"]]).status_code == 201
        assert (toys in candidate_ids(llm)) == open_then


def test_a_day_edit_keeps_the_hours_of_planned_places(
    visitor: TestClient, llm: FakeProvider, place_ids: dict[str, int]
) -> None:
    trip = saved_trip(
        visitor, llm, place_ids, ["Museum of Toys", "Testville Cathedral"], start_date=TUESDAY
    )
    # At 17:00 the 90-minute museum visit no longer fits before 18:00; the cathedral is open
    # until 20:00.
    at(visitor, datetime(2026, 11, 3, 17, 0, tzinfo=UTC))
    draft = drafted(visitor, trip, start={"lat": 45.0010, "lon": 7.0020})
    assert [s["name"] for s in stops(draft)] == ["Testville Cathedral"]
    [dropped] = draft["edit"]["dropped"]
    assert dropped["name"] == "Museum of Toys"
    assert dropped["reason"] == "It would be closed, or dark, by the time you get there."
