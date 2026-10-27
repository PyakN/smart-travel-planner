"""Category slugs known to the app. Must match the rows seeded by migrations 0001 and 0005."""

import re
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
    "nightlife",
    "restaurant",
]
CATEGORY_SLUGS: tuple[str, ...] = get_args(CategorySlug)

INDOOR_CATEGORIES = frozenset(
    {"museum", "gallery", "religious", "culture", "nightlife", "restaurant"}
)
# Landmarks with a building to go into, unlike walls, ruins, gates and aqueducts. OSM maps
# Lisbon's palaces as historic=castle with a castle_type.
INDOOR_HISTORIC = frozenset({"monastery", "building"})
INDOOR_CASTLE_TYPES = frozenset({"palace", "stately", "manor"})

# When a visit makes sense: "day" (indoors, closed at night), "daylight" (outdoors, needs
# light), "night" (bars, fado houses, restaurants: open in the evening) or "any".
VisitHours = Literal["any", "day", "daylight", "night"]
EVENING_CATEGORIES = frozenset({"nightlife", "restaurant"})
# Open until this late on some day (or past midnight): the place suits the evening too.
LATE_CLOSING_MIN = 22 * 60
_CLOSING_TIME = re.compile(r"-\s*(\d{1,2}):(\d{2})")


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


def closes_late(opening_hours: str | None) -> bool:
    """Whether OSM opening hours keep a place open late on some day: until 22:00 or later,
    past midnight, or 24/7. Days and exceptions are not evaluated: enough to tell the places
    that suit an evening (Mercado da Ribeira: "Th-Sa 10:00-02:00")."""
    if not opening_hours:
        return False
    if "24/7" in opening_hours:
        return True
    for hours, minutes in _CLOSING_TIME.findall(opening_hours):
        closing = int(hours) * 60 + int(minutes)
        if closing >= LATE_CLOSING_MIN or closing <= 5 * 60:  # 24:00, 00:00, 02:00
            return True
    return False


def visit_hours(category: str, tags: Mapping[str, str]) -> VisitHours:
    """When a place can be visited. Outdoor sights need daylight, except lit squares; indoor
    ones close at night unless their opening hours say they stay open late."""
    if category in EVENING_CATEGORIES:
        return "night"
    if is_outdoor(category, tags):
        lit = tags.get("lit") == "yes" or tags.get("place") == "square"
        return "any" if lit else "daylight"
    return "any" if closes_late(tags.get("opening_hours")) else "day"
