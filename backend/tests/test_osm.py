from typing import Any

from app.ingest.cities import CITIES
from app.ingest.osm import (
    PlaceRecord,
    build_query,
    categorize,
    deduplicate,
    normalize_name,
    parse_elements,
)


def node(osm_id: int, lat: float, lon: float, **tags: str) -> dict[str, Any]:
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


def way(osm_id: int, lat: float, lon: float, **tags: str) -> dict[str, Any]:
    return {"type": "way", "id": osm_id, "center": {"lat": lat, "lon": lon}, "tags": tags}


def record(osm_id: int, name: str, lat: float, lon: float, **tags: str) -> PlaceRecord:
    return PlaceRecord("node", osm_id, name, "landmark", lat, lon, {"name": name, **tags})


class TestCategorize:
    def test_museum_wins_over_landmark(self) -> None:
        assert categorize({"tourism": "museum", "historic": "palace"}) == "museum"

    def test_church_is_religious_even_if_attraction(self) -> None:
        assert categorize({"amenity": "place_of_worship", "tourism": "attraction"}) == "religious"

    def test_miradouro_is_viewpoint(self) -> None:
        assert categorize({"tourism": "viewpoint"}) == "viewpoint"

    def test_unknown_tags(self) -> None:
        assert categorize({"amenity": "bench"}) is None

    def test_evening_places(self) -> None:
        assert categorize({"amenity": "pub"}) == "nightlife"
        assert categorize({"amenity": "music_venue"}) == "nightlife"
        assert categorize({"amenity": "restaurant", "historic": "building"}) == "restaurant"

    def test_squares_are_landmarks_unless_something_else(self) -> None:
        assert categorize({"place": "square"}) == "landmark"
        assert categorize({"place": "square", "amenity": "marketplace"}) == "market"


class TestParseElements:
    def test_node_and_way_center(self) -> None:
        records = parse_elements(
            [
                node(1, 38.71, -9.13, name="Miradouro de Santa Luzia", tourism="viewpoint"),
                way(2, 38.69, -9.21, name="Torre de Belém", historic="tower"),
            ]
        )
        assert [(r.osm_type, r.category, r.lat) for r in records] == [
            ("node", "viewpoint", 38.71),
            ("way", "landmark", 38.69),
        ]

    def test_skips_unnamed_plaques_private_and_uncategorized(self) -> None:
        records = parse_elements(
            [
                node(1, 38.7, -9.1, tourism="viewpoint"),
                node(2, 38.7, -9.1, name="  ", tourism="viewpoint"),
                node(3, 38.7, -9.1, name="Plaque", historic="memorial", memorial="plaque"),
                node(4, 38.7, -9.1, name="Private garden", leisure="garden", access="private"),
                node(5, 38.7, -9.1, name="Bench", amenity="bench"),
                {"type": "way", "id": 6, "tags": {"name": "No center", "leisure": "park"}},
            ]
        )
        assert records == []

    def test_skips_closed_venues(self) -> None:
        records = parse_elements(
            [
                node(1, 38.7, -9.1, name="Cervejaria Solmar (Fechada)", amenity="pub"),
                node(2, 38.7, -9.1, name="Alma (closed)", amenity="restaurant", wikidata="Q1"),
                node(3, 38.7, -9.1, name="Pensão Amor", amenity="bar"),
            ]
        )
        assert [r.name for r in records] == ["Pensão Amor"]

    def test_only_fado_and_well_known_restaurants(self) -> None:
        records = parse_elements(
            [
                node(1, 38.7, -9.1, name="Tasca do Bairro", amenity="restaurant"),
                node(2, 38.7, -9.1, name="Clube de Fado", amenity="restaurant"),
                node(3, 38.7, -9.1, name="Tavares", amenity="restaurant", wikidata="Q10379683"),
            ]
        )
        assert [(r.name, r.category) for r in records] == [
            ("Clube de Fado", "restaurant"),
            ("Tavares", "restaurant"),
        ]

    def test_extracts_detail_tags(self) -> None:
        [place] = parse_elements(
            [
                node(
                    1,
                    38.7,
                    -9.1,
                    name="MAAT",
                    tourism="museum",
                    wikidata="Q24298530",
                    opening_hours="We-Mo 10:00-19:00",
                    **{"contact:website": "https://maat.pt"},
                )
            ]
        )
        assert place.wikidata == "Q24298530"
        assert place.opening_hours == "We-Mo 10:00-19:00"
        assert place.website == "https://maat.pt"


class TestDeduplicate:
    def test_merges_same_name_nearby_keeping_wikidata(self) -> None:
        entrance = record(1, "Mosteiro dos Jerónimos", 38.6979, -9.2064)
        outline = record(2, "Mosteiro dos Jeronimos", 38.6976, -9.2062, wikidata="Q193216")
        assert deduplicate([entrance, outline]) == [outline]

    def test_keeps_same_name_far_apart(self) -> None:
        a = record(1, "Jardim", 38.70, -9.10)
        b = record(2, "Jardim", 38.75, -9.15)
        assert len(deduplicate([a, b])) == 2

    def test_keeps_different_names_nearby(self) -> None:
        a = record(1, "Sé de Lisboa", 38.7098, -9.1334)
        b = record(2, "Igreja de Santo António", 38.7095, -9.1336)
        assert len(deduplicate([a, b])) == 2


def test_normalize_name() -> None:
    assert normalize_name("  Praça   do Comércio ") == "praca do comercio"


def test_build_query_covers_every_rule_and_bbox() -> None:
    query = build_query(CITIES["lisbon"].bbox)
    assert "(38.6913,-9.2298,38.7964,-9.0866)" in query
    for key in ("tourism", "historic", "amenity", "leisure", "place"):
        assert f'nwr["{key}"~' in query
    assert "viewpoint" in query and "place_of_worship" in query and "nightclub" in query
    assert query.endswith("out center tags;")
