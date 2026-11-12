from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.geo import BBox
from app.ingest.osm import normalize_name


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    bbox: BBox
    aliases: tuple[str, ...] = field(default=())
    # IANA name: trip dates, weather hours and daylight are in the city's local time.
    timezone: str = "UTC"
    # ISO 3166-1 alpha-2: the public holidays of opening hours ("PH off"). None where the
    # opening hours parser has no holidays for the country.
    country: str | None = None
    # An OSM relation the places must also lie in, where the bbox crosses a border that a
    # walk should not: Hong Kong's takes in Shenzhen, Singapore's Johor Bahru.
    boundary: int | None = None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def today(self) -> date:
        return datetime.now(self.tz).date()


def _city(
    slug: str,
    name: str,
    bbox: tuple[float, float, float, float],
    timezone: str,
    country: str | None,
    *aliases: str,
    boundary: int | None = None,
) -> City:
    """A city with its bbox as (south, west, north, east)."""
    return City(slug, name, BBox(*bbox), aliases, timezone, country, boundary)


# Each city's area is the bbox of its administrative boundary, unless a comment says
# otherwise. Lisbon comes first: it is the default city.
CITIES: dict[str, City] = {
    city.slug: city
    for city in (
        # Lisbon municipality (concelho de Lisboa).
        _city(
            "lisbon",
            "Lisbon",
            (38.6913, -9.2298, 38.7964, -9.0866),
            "Europe/Lisbon",
            "PT",
            "lisboa",
        ),
        # The state of Berlin. Its bbox takes in a rim of Brandenburg (Babelsberg, Teltow).
        _city("berlin", "Berlin", (52.3382, 13.0883, 52.6756, 13.7612), "Europe/Berlin", "DE"),
        # Barcelona municipality, Montjuïc and Collserola included.
        _city("barcelona", "Barcelona", (41.3170, 2.0524, 41.4680, 2.2284), "Europe/Madrid", "ES"),
        # Europe
        _city(
            "amsterdam", "Amsterdam", (52.2782, 4.7288, 52.4311, 5.0792), "Europe/Amsterdam", "NL"
        ),
        # The municipality, Piraeus not included.
        _city(
            "athens",
            "Athens",
            (37.9488, 23.6870, 38.0328, 23.7904),
            "Europe/Athens",
            "GR",
            "athina",
        ),
        # The Brussels-Capital Region.
        _city(
            "brussels",
            "Brussels",
            (50.7637, 4.2438, 50.9139, 4.4823),
            "Europe/Brussels",
            "BE",
            "bruxelles",
            "brussel",
        ),
        _city(
            "budapest", "Budapest", (47.3497, 18.9251, 47.6131, 19.3349), "Europe/Budapest", "HU"
        ),
        _city(
            "copenhagen",
            "Copenhagen",
            (55.6129, 12.4530, 55.7327, 12.7342),
            "Europe/Copenhagen",
            "DK",
            "københavn",
        ),
        # Dublin City.
        _city("dublin", "Dublin", (53.2987, -6.3870, 53.4105, -6.1149), "Europe/Dublin", "IE"),
        # The City of Edinburgh council area.
        _city(
            "edinburgh", "Edinburgh", (55.8188, -3.4495, 56.0041, -3.0750), "Europe/London", "GB"
        ),
        _city(
            "florence",
            "Florence",
            (43.7259, 11.1498, 43.8355, 11.3389),
            "Europe/Rome",
            "IT",
            "firenze",
        ),
        # The central districts on both shores, from Eyüp and Bakırköy's edge to the
        # Bosphorus bridges, Kadıköy and Üsküdar (the province spans 5,000 km²).
        _city(
            "istanbul", "Istanbul", (40.9600, 28.8600, 41.1200, 29.1200), "Europe/Istanbul", "TR"
        ),
        _city(
            "krakow",
            "Kraków",
            (49.9677, 19.7922, 50.1261, 20.2173),
            "Europe/Warsaw",
            "PL",
            "cracow",
        ),
        # Greater London.
        _city("london", "London", (51.2868, -0.5104, 51.6919, 0.3340), "Europe/London", "GB"),
        _city("madrid", "Madrid", (40.3120, -3.8890, 40.6437, -3.5183), "Europe/Madrid", "ES"),
        _city("milan", "Milan", (45.3867, 9.0409, 45.5358, 9.2781), "Europe/Rome", "IT", "milano"),
        _city(
            "munich",
            "Munich",
            (48.0616, 11.3608, 48.2481, 11.7229),
            "Europe/Berlin",
            "DE",
            "münchen",
            "muenchen",
        ),
        _city(
            "naples", "Naples", (40.7912, 14.1321, 40.9161, 14.3538), "Europe/Rome", "IT", "napoli"
        ),
        # The built-up city, without the Nordmarka forest.
        _city("oslo", "Oslo", (59.8100, 10.6200, 59.9800, 10.8700), "Europe/Oslo", "NO"),
        _city("paris", "Paris", (48.8156, 2.2241, 48.9022, 2.4698), "Europe/Paris", "FR"),
        _city(
            "porto", "Porto", (41.1384, -8.6913, 41.1859, -8.5521), "Europe/Lisbon", "PT", "oporto"
        ),
        _city(
            "prague", "Prague", (49.9419, 14.2244, 50.1774, 14.7068), "Europe/Prague", "CZ", "praha"
        ),
        # Roma Capitale, Ostia included.
        _city("rome", "Rome", (41.6556, 12.2344, 42.1410, 12.8558), "Europe/Rome", "IT", "roma"),
        _city(
            "seville",
            "Seville",
            (37.3002, -6.0329, 37.4530, -5.8192),
            "Europe/Madrid",
            "ES",
            "sevilla",
        ),
        # Stockholm Municipality.
        _city(
            "stockholm", "Stockholm", (59.2273, 17.7607, 59.4403, 18.2001), "Europe/Stockholm", "SE"
        ),
        _city("valencia", "Valencia", (39.2784, -0.4326, 39.5666, -0.2725), "Europe/Madrid", "ES"),
        # The municipality, the lagoon islands and Mestre included.
        _city(
            "venice", "Venice", (45.2312, 12.1668, 45.5780, 12.5966), "Europe/Rome", "IT", "venezia"
        ),
        _city(
            "vienna", "Vienna", (48.1179, 16.1818, 48.3227, 16.5775), "Europe/Vienna", "AT", "wien"
        ),
        _city(
            "warsaw",
            "Warsaw",
            (52.0978, 20.8517, 52.3682, 21.2712),
            "Europe/Warsaw",
            "PL",
            "warszawa",
        ),
        # The Americas
        _city(
            "buenos-aires",
            "Buenos Aires",
            (-34.7058, -58.5315, -34.5266, -58.3351),
            "America/Argentina/Buenos_Aires",
            "AR",
        ),
        # Mexico City (CDMX), the rural south included.
        _city(
            "mexico-city",
            "Mexico City",
            (19.0487, -99.3649, 19.5928, -98.9403),
            "America/Mexico_City",
            "MX",
            "ciudad de mexico",
            "cdmx",
        ),
        # The city of Montréal, on its island.
        _city(
            "montreal", "Montreal", (45.4101, -73.9742, 45.7048, -73.4743), "America/Toronto", "CA"
        ),
        # The five boroughs. Their bbox takes in Jersey City and Hoboken.
        _city(
            "new-york",
            "New York",
            (40.4766, -74.2588, 40.9176, -73.7002),
            "America/New_York",
            "US",
            "new york city",
            "nyc",
        ),
        _city(
            "rio-de-janeiro",
            "Rio de Janeiro",
            (-23.0827, -43.7963, -22.7461, -43.0991),
            "America/Sao_Paulo",
            "BR",
        ),
        # The city, without the Farallon Islands.
        _city(
            "san-francisco",
            "San Francisco",
            (37.7080, -122.5149, 37.8324, -122.3570),
            "America/Los_Angeles",
            "US",
        ),
        # The District of Columbia. Not "Washington", which names streets and squares
        # elsewhere (Washington Square in New York); "washington" from the LLM still
        # resolves (resolve_city).
        _city(
            "washington-dc",
            "Washington, D.C.",
            (38.7916, -77.1198, 38.9960, -76.9094),
            "America/New_York",
            "US",
            "washington dc",
            "washington d.c.",
            "washington d c",
        ),
        # Asia
        # Bangkok's holidays are not in the opening hours parser.
        _city("bangkok", "Bangkok", (13.2191, 100.3279, 13.9552, 100.9386), "Asia/Bangkok", None),
        # The city, without Hatta and the desert (the emirate spans 4,000 km²).
        _city("dubai", "Dubai", (25.0300, 55.0500, 25.3600, 55.4500), "Asia/Dubai", None),
        # Places only from Hong Kong itself: its bbox takes in Shenzhen.
        _city(
            "hong-kong",
            "Hong Kong",
            (22.1367, 113.8171, 22.5683, 114.5024),
            "Asia/Hong_Kong",
            "HK",
            "hongkong",
            boundary=913110,
        ),
        # The city, mountains included.
        _city("kyoto", "Kyoto", (34.8749, 135.5590, 35.3212, 135.8784), "Asia/Tokyo", "JP"),
        _city("seoul", "Seoul", (37.4285, 126.7644, 37.7015, 127.1838), "Asia/Seoul", "KR"),
        # The main island and Sentosa, without the outlying islands. Places only from
        # Singapore itself: its bbox takes in Johor Bahru.
        _city(
            "singapore",
            "Singapore",
            (1.2000, 103.6000, 1.4800, 104.0500),
            "Asia/Singapore",
            "SG",
            boundary=536780,
        ),
        _city("taipei", "Taipei", (24.9605, 121.4571, 25.2103, 121.6659), "Asia/Taipei", None),
        # The 23 special wards (Tokyo Metropolis reaches the Pacific islands).
        _city("tokyo", "Tokyo", (35.5200, 139.5600, 35.8200, 139.9200), "Asia/Tokyo", "JP"),
        # Africa and Oceania
        # The City Bowl, the Atlantic seaboard, Table Mountain and Kirstenbosch (the metro
        # spans 2,400 km², Cape Point included).
        _city(
            "cape-town",
            "Cape Town",
            (-34.0500, 18.3500, -33.8000, 18.5500),
            "Africa/Johannesburg",
            "ZA",
        ),
        _city(
            "marrakesh",
            "Marrakesh",
            (31.5442, -8.0893, 31.7104, -7.8847),
            "Africa/Casablanca",
            "MA",
            "marrakech",
        ),
        # The centre, the harbour, Bondi and Manly (Greater Sydney spans 12,000 km²).
        _city(
            "sydney", "Sydney", (-33.9500, 151.1000, -33.7800, 151.3000), "Australia/Sydney", "AU"
        ),
    )
}


def resolve_city(name: str) -> City | None:
    """Supported city for a name the traveller used (slug, English name or alias), accents
    ignored. A name before a comma counts too: "washington" for Washington, D.C."""
    key = normalize_name(name)
    for city in CITIES.values():
        names = (city.slug, city.name, city.name.split(",")[0], *city.aliases)
        if key in {normalize_name(n) for n in names}:
            return city
    return None
