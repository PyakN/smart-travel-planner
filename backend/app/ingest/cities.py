from dataclasses import dataclass, field

from app.geo import BBox


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    bbox: BBox
    aliases: tuple[str, ...] = field(default=())


CITIES: dict[str, City] = {
    # Lisbon municipality (concelho de Lisboa).
    "lisbon": City(
        "lisbon", "Lisbon", BBox(38.6913, -9.2298, 38.7964, -9.0866), aliases=("lisboa",)
    ),
}


def resolve_city(name: str) -> City | None:
    """Supported city for a name the traveller used (slug, English name or alias)."""
    key = " ".join(name.split()).lower()
    for city in CITIES.values():
        if key in (city.slug, city.name.lower(), *city.aliases):
            return city
    return None
