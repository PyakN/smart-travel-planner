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
    # ISO 3166-1 alpha-2: the public holidays of opening hours ("PH off").
    country: str | None = None

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
        country="PT",
    ),
    # The state of Berlin. Its bbox takes in a rim of Brandenburg (Babelsberg, Teltow).
    "berlin": City(
        "berlin",
        "Berlin",
        BBox(52.3382, 13.0883, 52.6756, 13.7612),
        timezone="Europe/Berlin",
        country="DE",
    ),
    # Barcelona municipality, Montjuïc and Collserola included.
    "barcelona": City(
        "barcelona",
        "Barcelona",
        BBox(41.3170, 2.0524, 41.4680, 2.2284),
        timezone="Europe/Madrid",
        country="ES",
    ),
}


def resolve_city(name: str) -> City | None:
    """Supported city for a name the traveller used (slug, English name or alias)."""
    key = " ".join(name.split()).lower()
    for city in CITIES.values():
        if key in (city.slug, city.name.lower(), *city.aliases):
            return city
    return None
