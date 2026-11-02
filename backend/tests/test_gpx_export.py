"""A plan as a GPX file (app.services.gpx_export)."""

from typing import Any
from xml.etree import ElementTree as ET

import pytest

from app.schemas.plan import PlanResponse
from app.services.gpx_export import GPX_NAMESPACE, gpx_filename, plan_gpx

NS = {"gpx": GPX_NAMESPACE}


def stop(place_id: int, name: str, arrive: str, leave: str, **extra: Any) -> dict[str, Any]:
    return {
        "place_id": place_id,
        "name": name,
        "category": "landmark",
        "lat": 38.71 + place_id / 1000,
        "lon": -9.13,
        "arrive": arrive,
        "leave": leave,
        "travel_mode": "walk",
        "travel_min": 10,
        "distance_from_previous_m": 800,
        **extra,
    }


def day(number: int, stops: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "day": number,
        "stops": stops,
        "distance_m": 2400,
        "walking_m": 2400,
        "transit_legs": 0,
        "duration_min": 300,
        "self_intersections": 0,
        "segments": [
            {"mode": "walk", "geometry": [[-9.13, 38.711], [-9.131, 38.712], [-9.13, 38.713]]},
            {"mode": "transit", "geometry": [[-9.13, 38.713]]},
        ],
        **extra,
    }


def plan(days: list[dict[str, Any]], **extra: Any) -> PlanResponse:
    return PlanResponse.model_validate(
        {
            "id": 12,
            "request_text": "Two days of castles & <viewpoints>",
            "city": "lisbon",
            "trip": {
                "city": "lisbon",
                "days": len(days),
                "interests": [],
                "avoid": [],
                "pace": "moderate",
                "keywords": [],
                "notes": "",
            },
            "rationale": "",
            "days": days,
            "total_distance_m": 4800,
            "distance_source": "osrm",
            "strategy": "kmeans",
            "dropped": [],
            "warnings": [],
            "timings_ms": {},
            **extra,
        }
    )


TWO_DAYS = [
    day(
        1,
        [
            stop(1, "Castelo de São Jorge", "09:30", "10:30", note="The best view."),
            stop(2, "Sé", "10:45", "11:30", website="https://se.example"),
        ],
        date="2026-11-03",
        start="09:30",
    ),
    day(2, [stop(3, "Torre de Belém", "10:00", "10:45")], date="2026-11-04", start="09:30"),
]


def parse(document: bytes) -> ET.Element:
    assert document.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    return ET.fromstring(document)


def texts(root: ET.Element, path: str) -> list[str]:
    return [element.text or "" for element in root.findall(path, NS)]


def test_every_stop_is_a_waypoint_and_every_day_a_track() -> None:
    root = parse(plan_gpx(plan(TWO_DAYS)))

    assert root.tag == f"{{{GPX_NAMESPACE}}}gpx"
    assert root.get("version") == "1.1"
    assert texts(root, "gpx:metadata/gpx:name") == ["2 days in Lisbon"]
    assert texts(root, "gpx:metadata/gpx:desc") == ["Two days of castles & <viewpoints>"]
    assert texts(root, "gpx:wpt/gpx:name") == [
        "1.1 Castelo de São Jorge",
        "1.2 Sé",
        "2.1 Torre de Belém",
    ]
    first = root.findall("gpx:wpt", NS)[0]
    assert (first.get("lat"), first.get("lon")) == ("38.711000", "-9.130000")
    assert texts(root, "gpx:wpt/gpx:desc")[:2] == [
        "Day 1, stop 1: 09:30–10:30.\n\nThe best view.",
        "Day 1, stop 2: 10:45–11:30.",
    ]
    assert texts(root, "gpx:wpt/gpx:type") == ["landmark"] * 3
    links = root.findall("gpx:wpt/gpx:link", NS)
    assert [link.get("href") for link in links] == ["https://se.example"]

    assert texts(root, "gpx:trk/gpx:name") == ["Day 1", "Day 2"]
    assert texts(root, "gpx:trk/gpx:desc")[0] == "Tue 3 Nov 2026: 2.4 km on foot, 09:30–11:30"
    # A lone point is no segment.
    segments = root.findall("gpx:trk[1]/gpx:trkseg", NS)
    assert len(segments) == 1
    assert len(segments[0].findall("gpx:trkpt", NS)) == 3


def test_waypoint_times_are_arrivals_in_utc() -> None:
    root = parse(plan_gpx(plan(TWO_DAYS)))
    # Lisbon keeps UTC in November.
    assert texts(root, "gpx:wpt/gpx:time") == [
        "2026-11-03T09:30:00Z",
        "2026-11-03T10:45:00Z",
        "2026-11-04T10:00:00Z",
    ]


def test_times_past_midnight_are_the_next_day() -> None:
    late = day(
        1,
        [
            stop(1, "Lantern Square", "23:40", "00:10"),
            stop(2, "Night Market", "00:25", "01:00"),
        ],
        date="2026-07-01",
        start="22:00",
    )
    root = parse(plan_gpx(plan([late])))
    # Lisbon is UTC+1 in summer.
    assert texts(root, "gpx:wpt/gpx:time") == ["2026-07-01T22:40:00Z", "2026-07-01T23:25:00Z"]


def test_one_day_numbers_stops_alone() -> None:
    root = parse(plan_gpx(plan(TWO_DAYS), day=2))

    assert texts(root, "gpx:metadata/gpx:name") == ["2 days in Lisbon: day 2"]
    assert texts(root, "gpx:wpt/gpx:name") == ["1. Torre de Belém"]
    assert texts(root, "gpx:trk/gpx:name") == ["Day 2"]


def test_start_point_and_plans_without_dates() -> None:
    undated = [day(1, [stop(1, "Sé", "09:30", "10:00")], transit_legs=1)]
    root = parse(plan_gpx(plan(undated, start={"lat": 38.72, "lon": -9.14, "round_trip": True})))

    assert texts(root, "gpx:wpt/gpx:name") == ["Start and end", "1. Sé"]
    assert texts(root, "gpx:wpt/gpx:type") == ["start", "landmark"]
    assert root.findall("gpx:wpt/gpx:time", NS) == []
    assert texts(root, "gpx:trk/gpx:desc") == ["2.4 km on foot, 1 transit ride, 09:30–10:00"]


def test_a_day_not_in_the_plan() -> None:
    with pytest.raises(ValueError):
        plan_gpx(plan(TWO_DAYS), day=3)


def test_filename() -> None:
    assert gpx_filename(plan(TWO_DAYS)) == "lisbon-plan-12.gpx"
    assert gpx_filename(plan(TWO_DAYS), 2) == "lisbon-plan-12-day-2.gpx"
