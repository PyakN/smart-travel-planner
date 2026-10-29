from pydantic import BaseModel, Field


class CityOut(BaseModel):
    slug: str = Field(description="`city` in POST /plan, GET /places and GET /categories")
    name: str
    timezone: str = Field(description="IANA time zone: trip dates and hours are the city's")
    bbox: tuple[float, float, float, float] = Field(
        description="west, south, east, north: where its places are (bbox in GET /places)"
    )
