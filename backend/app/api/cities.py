from fastapi import APIRouter

from app.ingest.cities import CITIES
from app.schemas.city import CityOut

router = APIRouter(tags=["cities"])


@router.get("/cities")
async def list_cities() -> list[CityOut]:
    """The cities plans can be made for."""
    return [
        CityOut(
            slug=city.slug,
            name=city.name,
            timezone=city.timezone,
            bbox=(city.bbox.west, city.bbox.south, city.bbox.east, city.bbox.north),
        )
        for city in CITIES.values()
    ]
