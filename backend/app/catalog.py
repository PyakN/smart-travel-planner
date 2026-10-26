"""Category slugs known to the app. Must match the rows seeded by migration 0001."""

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
