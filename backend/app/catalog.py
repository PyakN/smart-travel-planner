"""Category slugs known to the app. Must match the rows seeded by migration 0001."""

from collections.abc import Mapping
from typing import Literal, get_args

CategorySlug = Literal[
    "museum",
    "gallery",
    "landmark",
    "monument",
    "viewpoint",
    "religious",
    "park",
    "culture",
    "market",
    "attraction",
]
CATEGORY_SLUGS: tuple[str, ...] = get_args(CategorySlug)

INDOOR_CATEGORIES = frozenset({"museum", "gallery", "religious", "culture"})
# Landmarks with a building to go into, unlike walls, ruins, gates and aqueducts. OSM maps
# Lisbon's palaces as historic=castle with a castle_type.
INDOOR_HISTORIC = frozenset({"monastery", "building"})
INDOOR_CASTLE_TYPES = frozenset({"palace", "stately", "manor"})


def is_outdoor(category: str, tags: Mapping[str, str]) -> bool:
    """Whether a visit happens in the open air, so rain, fog and darkness spoil it."""
    if tags.get("indoor") == "yes" or tags.get("covered") == "yes":
        return False
    if category in INDOOR_CATEGORIES:
        return False
    if category == "market":
        return "building" not in tags  # market halls are mapped as buildings
    if category == "landmark":
        historic = tags.get("historic")
        palace = historic == "castle" and tags.get("castle_type") in INDOOR_CASTLE_TYPES
        return not (palace or historic in INDOOR_HISTORIC)
    if category == "attraction":
        return tags.get("tourism") != "aquarium"  # mostly fountains, trees, squares, lifts
    return True  # viewpoints, parks, monuments (statues, memorials, public art)
