"""The self-hosted OSRM (osrm/) routes in every supported city, with room around it."""

from pathlib import Path

import pytest

from app.geo import BBox
from app.ingest.cities import CITIES

AREAS = Path(__file__).resolve().parents[2] / "osrm" / "areas.txt"
MARGIN_DEG = 0.05


def read_areas() -> list[tuple[str, str, BBox]]:
    areas = []
    for line in AREAS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        city, region, bbox = line.split()
        west, south, east, north = (float(v) for v in bbox.split(","))
        areas.append((city, region, BBox(south=south, west=west, north=north, east=east)))
    return areas


def test_areas_are_supported_cities() -> None:
    areas = read_areas()
    assert areas
    assert {city for city, _, _ in areas} == set(CITIES)
    # A region may serve several cities (prepare.sh downloads it once), but a city's
    # lines are cut out of different regions.
    assert len({(city, region) for city, region, _ in areas}) == len(areas)


@pytest.mark.parametrize("slug", sorted(CITIES))
def test_each_city_is_covered_with_a_margin(slug: str) -> None:
    city = CITIES[slug].bbox
    boxes = [bbox for name, _, bbox in read_areas() if name == slug]
    for box in boxes:
        assert box.west <= city.west - MARGIN_DEG
        assert box.south <= city.south - MARGIN_DEG
        assert box.east >= city.east + MARGIN_DEG
        assert box.north >= city.north + MARGIN_DEG
