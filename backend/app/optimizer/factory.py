from app.config import Settings
from app.optimizer.distance import DistanceProvider, HaversineProvider, OsrmProvider


def create_distance_provider(settings: Settings) -> DistanceProvider:
    if settings.routing_provider == "haversine":
        return HaversineProvider()
    return OsrmProvider(settings.osrm_base_url, timeout_s=settings.osrm_timeout_s)
