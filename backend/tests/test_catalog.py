import pytest

from app.catalog import VisitHours, closes_late, is_outdoor, visit_hours


@pytest.mark.parametrize(
    ("category", "tags", "outdoor"),
    [
        ("viewpoint", {}, True),
        ("park", {"leisure": "garden"}, True),
        ("monument", {"tourism": "artwork"}, True),
        ("monument", {"tourism": "artwork", "indoor": "yes"}, False),
        ("museum", {}, False),
        ("gallery", {}, False),
        ("religious", {"amenity": "place_of_worship"}, False),
        ("culture", {"amenity": "theatre"}, False),
        # Castelo de São Jorge vs Palácio Nacional da Ajuda: both historic=castle.
        ("landmark", {"historic": "castle", "castle_type": "fortress"}, True),
        ("landmark", {"historic": "castle", "castle_type": "palace"}, False),
        ("landmark", {"historic": "monastery"}, False),
        ("landmark", {"historic": "aqueduct"}, True),
        ("landmark", {}, True),
        # Mercado da Ribeira (a hall) vs Feira da Ladra (stalls on a square).
        ("market", {"amenity": "marketplace", "building": "retail"}, False),
        ("market", {"amenity": "marketplace"}, True),
        ("market", {"amenity": "marketplace", "covered": "yes"}, False),
        ("attraction", {"tourism": "aquarium"}, False),
        ("attraction", {"tourism": "zoo"}, True),
        ("attraction", {"historic": "fountain", "building": "yes"}, True),
        ("nightlife", {"amenity": "bar"}, False),
        ("restaurant", {"amenity": "restaurant"}, False),
        ("landmark", {"place": "square"}, True),
    ],
)
def test_is_outdoor(category: str, tags: dict[str, str], outdoor: bool) -> None:
    assert is_outdoor(category, tags) is outdoor


# Opening hours as Lisbon's places have them in OpenStreetMap.
@pytest.mark.parametrize(
    ("opening_hours", "late"),
    [
        ("Mo-We 10:00-00:00; Th-Sa 10:00-02:00; Su 10:00-24:00", True),  # Mercado da Ribeira
        ("Sa-Su 19:30-00:00; Mo-Fr 12:00-00:00", True),  # Chapitô
        ("Mo-Su 07:00-23:00", True),
        ("24/7", True),
        ("Tu-Su 10:00-18:00; Jan 01,Dec 25 off", False),
        ("Mo-Fr 12:00-15:00,19:00-21:30", False),
        ("", False),
        (None, False),
    ],
)
def test_closes_late(opening_hours: str | None, late: bool) -> None:
    assert closes_late(opening_hours) is late


@pytest.mark.parametrize(
    ("category", "tags", "hours"),
    [
        ("museum", {"opening_hours": "Tu-Su 10:00-18:00"}, "day"),
        ("religious", {}, "day"),
        ("market", {"building": "retail", "opening_hours": "Th-Sa 10:00-02:00"}, "any"),
        ("culture", {"amenity": "arts_centre", "opening_hours": "We-Sa 18:00-02:00"}, "any"),
        ("viewpoint", {}, "daylight"),
        # A park open until midnight is still dark at night.
        ("park", {"opening_hours": "Mo-Su 07:00-24:00"}, "daylight"),
        ("landmark", {"place": "square"}, "any"),
        ("monument", {"lit": "yes"}, "any"),
        ("nightlife", {"amenity": "bar"}, "night"),
        ("restaurant", {"amenity": "restaurant"}, "night"),
    ],
)
def test_visit_hours(category: str, tags: dict[str, str], hours: VisitHours) -> None:
    assert visit_hours(category, tags) == hours
