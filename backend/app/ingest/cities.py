from dataclasses import dataclass


@dataclass(frozen=True)
class BBox:
    south: float
    west: float
    north: float
    east: float


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    bbox: BBox


CITIES: dict[str, City] = {
    # Lisbon municipality (concelho de Lisboa).
    "lisbon": City("lisbon", "Lisbon", BBox(38.6913, -9.2298, 38.7964, -9.0866)),
}
