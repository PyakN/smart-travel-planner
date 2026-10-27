from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.geo import BBox


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    bbox: BBox
    aliases: tuple[str, ...] = field(default=())
    # IANA name: trip dates, weather hours and daylight are in the city's local time.
    timezone: str = "UTC"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def today(self) -> date:
        return datetime.now(self.tz).date()


CITIES: dict[str, City] = {
    # Lisbon municipality (concelho de Lisboa).
    "lisbon": City(
        "lisbon",
        "Lisbon",
        BBox(38.6913, -9.2298, 38.7964, -9.0866),
        aliases=("lisboa",),
        timezone="Europe/Lisbon",
    ),
}


def resolve_city(name: str) -> City | None:
    """Supported city for a name the traveller used (slug, English name or alias)."""
    key = " ".join(name.split()).lower()
    for city in CITIES.values():
        if key in (city.slug, city.name.lower(), *city.aliases):
            return city
    return None
