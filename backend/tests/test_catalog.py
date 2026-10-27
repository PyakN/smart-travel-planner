import pytest

from app.catalog import is_outdoor


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
