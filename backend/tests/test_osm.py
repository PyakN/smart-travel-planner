import asyncio
import re
from pathlib import Path
from typing import Any

import httpx

from app.ingest.cities import CITIES
from app.ingest.osm import (
    KEPT_TAG_PREFIXES,
    KEPT_TAGS,
    OVERPASS_URLS,
    PlaceRecord,
    build_query,
    categorize,
    deduplicate,
    fetch_elements,
    kept_tags,
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

    def test_food_and_drink(self) -> None:
        assert categorize({"amenity": "pub"}) == "nightlife"
        assert categorize({"amenity": "music_venue"}) == "nightlife"
        assert categorize({"amenity": "restaurant", "historic": "building"}) == "restaurant"
        assert categorize({"amenity": "fast_food"}) == "restaurant"
        assert categorize({"amenity": "cafe", "historic": "building"}) == "cafe"
        assert categorize({"amenity": "ice_cream"}) == "cafe"
        # Pastéis de Belém: a pastry shop, even though it is an attraction.
        assert categorize({"shop": "pastry", "tourism": "attraction"}) == "cafe"

    def test_buildings_mapped_as_artworks(self) -> None:
        # Casa Batlló opens to visitors: a landmark. Casa Calvet is flats: a façade to see.
        batllo = {
            "tourism": "artwork",
            "artwork_type": "architecture",
            "building": "apartments",
            "historic": "heritage",
            "opening_hours": "Mo-Su 09:00-21:00",
        }
        assert categorize(batllo) == "landmark"
        calvet = {k: v for k, v in batllo.items() if k != "opening_hours"}
        assert categorize(calvet) == "monument"
        assert categorize({**batllo, "tourism": "museum"}) == "museum"
        # A memorial is a memorial, whatever it is mapped as too.
        assert categorize({**batllo, "historic": "memorial"}) == "monument"

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

    def test_skips_venues_whose_hours_say_they_closed(self) -> None:
        closed = {"opening_hours": "Fechado permanentemente"}
        records = parse_elements(
            [
                node(1, 38.7, -9.1, name="Amuse Bouche", amenity="restaurant", **closed),
                node(2, 38.7, -9.1, name="Sushi", amenity="restaurant", opening_hours="closed"),
                node(3, 38.7, -9.1, name="Tasca", amenity="restaurant", opening_hours="Su off"),
                # Sights stay: a museum closed for works opens again.
                node(4, 38.7, -9.1, name="Museu do Azulejo", tourism="museum", **closed),
            ]
        )
        assert [r.name for r in records] == ["Tasca", "Museu do Azulejo"]

    def test_skips_closed_places_in_german_spanish_and_catalan(self) -> None:
        def cafe(osm_id: int, name: str, **tags: str) -> dict[str, Any]:
            return node(osm_id, 52.5, 13.4, name=name, amenity="cafe", **tags)

        records = parse_elements(
            [
                node(1, 52.5, 13.4, name="Das Verborgene Museum (geschlossen)", tourism="museum"),
                cafe(2, "Kantine (bis vsl 2027 geschlossen)"),
                cafe(3, "Bar Pinotxo (Tancat)"),
                cafe(4, "Casa Lola (cerrada)"),
                cafe(5, "AM to PM", opening_hours="zurzeit geschlossen"),
                cafe(6, "Ma Maison", opening_hours="Vorübergehend geschlossen"),
                cafe(7, "Planxados", opening_hours="Cerrado permanentemente"),
                cafe(8, "Xurreria", opening_hours="Tancat temporalment"),
                # Closed on one day only, and a memorial to a sit-in ("tancada"), stay.
                cafe(9, "Curry 36", opening_hours="Mo geschlossen"),
                node(10, 41.4, 2.2, name="La tancada de dones", historic="memorial"),
            ]
        )
        assert [r.name for r in records] == ["Curry 36", "La tancada de dones"]

    def test_skips_closed_places_in_the_other_cities_languages(self) -> None:
        def cafe(osm_id: int, name: str, **tags: str) -> dict[str, Any]:
            return node(osm_id, 48.9, 2.3, name=name, amenity="cafe", **tags)

        records = parse_elements(
            [
                cafe(1, "Le Petit Café (Fermé)"),
                cafe(2, "Bar Gino (chiuso)"),
                cafe(3, "Café Hoppe (gesloten)"),
                cafe(4, "Kavárna Slavia (zavřeno)"),
                cafe(5, "Kawiarnia Noworolski (zamknięte)"),
                cafe(6, "Kávéház (zárva)"),
                cafe(7, "Kaffebar (stängt)"),
                cafe(8, "Kahve Dünyası (kapandı)"),
                cafe(9, "Καφενείο (κλειστό)"),
                cafe(10, "喫茶ルノアール（閉店）"),
                cafe(11, "カフェ (2023年閉店)"),
                cafe(12, "카페 (폐업)"),
                cafe(13, "Chez Paul", opening_hours="Fermé définitivement"),
                cafe(14, "Caffè Rosati", opening_hours="temporaneamente chiuso"),
                cafe(15, "Brownies", opening_hours="tijdelijk gesloten"),
                cafe(16, "Kafé", opening_hours="midlertidig lukket"),
                cafe(17, "Lokanta", opening_hours="geçici olarak kapalı"),
                cafe(18, "喫茶", opening_hours="閉店"),
                # Closed on Mondays only, and names that only contain a closing word, stay.
                cafe(19, "Trattoria", opening_hours="Mo chiuso; Tu-Su 12:00-23:00"),
                node(20, 41.0, 28.97, name="Grand Bazaar (Kapalı Çarşı)", amenity="marketplace"),
                cafe(21, "La Ferme (Paris)"),
                cafe(22, "閉店セール"),
            ]
        )
        assert [r.name for r in records] == [
            "Trattoria",
            "Grand Bazaar (Kapalı Çarşı)",
            "La Ferme (Paris)",
            "閉店セール",
        ]

    def test_every_named_venue(self) -> None:
        records = parse_elements(
            [
                node(1, 38.7, -9.1, name="Tasca do Bairro", amenity="restaurant"),
                node(2, 38.7, -9.1, name="Clube de Fado", amenity="restaurant"),
                node(3, 38.7, -9.1, name="A Brasileira", amenity="cafe", cuisine="coffee_shop"),
                node(4, 38.7, -9.1, name="Santini", amenity="ice_cream"),
                node(5, 38.7, -9.1, name="Manteigaria", shop="pastry", **{"diet:vegan": "no"}),
                node(6, 38.7, -9.1, name="Pizza Hut", amenity="fast_food"),
                node(7, 38.7, -9.1, amenity="cafe"),
            ]
        )
        assert [(r.name, r.category) for r in records] == [
            ("Tasca do Bairro", "restaurant"),
            ("Clube de Fado", "restaurant"),
            ("A Brasileira", "cafe"),
            ("Santini", "cafe"),
            ("Manteigaria", "cafe"),
            ("Pizza Hut", "restaurant"),
        ]
        assert records[2].tags["cuisine"] == "coffee_shop"
        assert records[4].tags["diet:vegan"] == "no"

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

    def test_names_in_another_script_go_by_their_english_or_romanized_name(self) -> None:
        def sight(osm_id: int, **names: str) -> dict[str, Any]:
            return node(osm_id, 35.7, 139.8, tourism="attraction", **names)

        records = parse_elements(
            [
                sight(1, name="浅草寺", **{"name:en": "Sensō-ji", "name:ja-Latn": "Sensōji"}),
                sight(2, name="Ακρόπολη", int_name="Akropoli"),
                sight(3, name="東京駅", **{"name:ja-Latn": "Tōkyō-eki", "name:ja_rm": "Tokyo eki"}),
                sight(4, name="香港文化中心 Hong Kong Cultural Centre", **{"name:en": "HKCC"}),
                # No Latin name to go by, or one in the same script: the OSM name stays.
                sight(5, name="ラーメン一蘭", **{"name:en": "一蘭"}),
                # Latin names stay as OSM has them, ª and º too.
                sight(6, name="Largo 1º de Dezembro", **{"name:en": "1st December Square"}),
                sight(7, name="Torre de Belém", **{"name:en": "Belém Tower"}),
            ]
        )
        assert [r.name for r in records] == [
            "Sensō-ji",
            "Akropoli",
            "Tōkyō-eki",
            "HKCC",
            "ラーメン一蘭",
            "Largo 1º de Dezembro",
            "Torre de Belém",
        ]
        # The OSM name stays in the tags (the name search looks there too).
        assert records[0].tags["name"] == "浅草寺"

    def test_a_place_going_by_its_english_name_closed_by_its_own(self) -> None:
        renoir = {"name": "喫茶ルノアール（閉店）", "int_name": "Renoir"}
        kissa = {"name": "喫茶", "name:en": "Kissa (closed)"}
        records = parse_elements(
            [
                node(1, 35.7, 139.8, amenity="cafe", **renoir),
                node(2, 35.7, 139.8, amenity="cafe", **kissa),
            ]
        )
        assert records == []


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
    for key in ("tourism", "historic", "amenity", "leisure", "place", "shop"):
        assert f'nwr["{key}"~' in query
    assert "viewpoint" in query and "place_of_worship" in query and "nightclub" in query
    assert "ice_cream" in query and "pastry" in query
    assert query.endswith("out center tags;")


def test_build_query_keeps_places_within_a_boundary() -> None:
    # Hong Kong's bbox takes in Shenzhen: its places come from inside Hong Kong only.
    hong_kong = CITIES["hong-kong"]
    query = build_query(hong_kong.bbox, boundary=hong_kong.boundary)
    selectors = [line for line in query.splitlines() if line.startswith("  nwr[")]
    assert selectors
    assert all(
        line.endswith("(22.1367,113.8171,22.5683,114.5024)(area:3600913110);") for line in selectors
    )
    assert "area:" not in build_query(CITIES["lisbon"].bbox, boundary=CITIES["lisbon"].boundary)


def test_fetch_elements_skips_a_mirror_whose_query_ran_out_of_time() -> None:
    answers = {
        OVERPASS_URLS[0]: {
            "elements": [{"id": 1}],
            "remark": 'runtime error: Query timed out in "query" at line 3 after 181 seconds.',
        },
        OVERPASS_URLS[1]: {"elements": [{"id": 1}, {"id": 2}]},
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=answers[str(request.url)])
    )

    async def fetch() -> list[dict[str, Any]]:
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_elements("[out:json];", client)

    assert asyncio.run(fetch()) == [{"id": 1}, {"id": 2}]


def test_fetch_elements_tries_every_mirror_in_turn() -> None:
    tried: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        tried.append(str(request.url))
        if str(request.url) == OVERPASS_URLS[-1]:
            return httpx.Response(200, json={"elements": [{"id": 1}]})
        return httpx.Response(502)

    async def fetch() -> list[dict[str, Any]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
            return await fetch_elements("[out:json];", client)

    assert asyncio.run(fetch()) == [{"id": 1}]
    assert tried == list(OVERPASS_URLS)


def test_kept_tags_leave_out_what_the_app_does_not_read() -> None:
    tags = {
        "name": "Café A Brasileira",
        "amenity": "cafe",
        "diet:vegan": "limited",
        "opening_hours": "Mo-Su 08:00-02:00",
        "addr:street": "Rua Garrett",
        "check_date": "2025-06-01",
        "name:de": "Café Brasileira",
        # Names to go by (display_name) stay.
        "int_name": "A Brasileira",
        "name:pt-Latn": "A Brasileira",
    }
    assert kept_tags(tags) == {
        "name": "Café A Brasileira",
        "amenity": "cafe",
        "diet:vegan": "limited",
        "opening_hours": "Mo-Su 08:00-02:00",
        "int_name": "A Brasileira",
        "name:pt-Latn": "A Brasileira",
    }


APP_DIR = Path(__file__).resolve().parents[1] / "app"
# A tag read by name: tags.get("lit"), tags["name:en"], "building" in tags, has_key("...").
TAG_READ = re.compile(
    r"""tags(?:\.get\(|\[|\.has_key\()\s*"([^"]+)"|"([^"]+)"\s+(?:not\s+)?in\s+(?:\w+\.)?tags\b"""
)


def test_the_app_reads_only_kept_tags() -> None:
    # The importer reads every tag (names to go by, closed places) before it keeps some.
    importer = APP_DIR / "ingest" / "osm.py"
    read = {
        key
        for path in APP_DIR.rglob("*.py")
        if path != importer
        for match in TAG_READ.finditer(path.read_text(encoding="utf-8"))
        for key in match.groups()
        if key
    }
    assert read, "the pattern finds no tag reads"
    assert {k for k in read if k not in KEPT_TAGS and not k.startswith(KEPT_TAG_PREFIXES)} == set()
