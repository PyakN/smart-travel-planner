from app.config import Settings
from app.optimizer.distance import DistanceProvider, HaversineProvider, OsrmProvider
from app.optimizer.transit import HereTransitProvider, TransitProvider


def create_distance_provider(settings: Settings) -> DistanceProvider:
    if settings.routing_provider == "haversine":
        return HaversineProvider()
    return OsrmProvider(settings.osrm_base_url, timeout_s=settings.osrm_timeout_s)


def create_transit_provider(settings: Settings) -> TransitProvider | None:
    """HERE public transport routes; None (estimated ride times) without a key."""
    if settings.transit_provider == "estimate" or not settings.here_api_key:
        return None
    return HereTransitProvider(
        settings.here_api_key.get_secret_value(),
        url=settings.here_transit_url,
        timeout_s=settings.here_timeout_s,
    )
