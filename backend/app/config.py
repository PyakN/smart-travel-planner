from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives at the repo root; commands usually run from backend/.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str
    default_city: str = "lisbon"
    # Upper bound for POST /plan end to end (two LLM calls with retries + routing).
    plan_timeout_s: float = 90.0

    llm_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    # Empty means the provider's default (see app.llm.factory).
    llm_model: str | None = None
    llm_fallback_model: str | None = None
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2
    # Room for a short note per place: a 7-day intense trip has 56 of them.
    llm_max_output_tokens: int = 4096
    llm_daily_token_budget: int = 1_000_000
    llm_cache_size: int = 256

    # Walking distances: OSRM foot routing (public FOSSGIS server by default), with a
    # haversine fallback when it is unavailable.
    routing_provider: Literal["osrm", "haversine"] = "osrm"
    osrm_base_url: str = "https://routing.openstreetmap.de/routed-foot"
    osrm_timeout_s: float = 10.0

    # Public transport: real routes and timetables from HERE when a key is set; otherwise
    # ride times are a fixed-speed estimate (app.optimizer.planner).
    transit_provider: Literal["here", "estimate"] = "here"
    here_api_key: SecretStr | None = None
    here_transit_url: str = "https://transit.router.hereapi.com/v8/routes"
    here_timeout_s: float = 8.0

    # Weather: OpenWeatherMap's 5 day / 3 hour forecast, shown with every plan and used by
    # weather-aware plans (app.services.weather_service). Without a key, plans go without.
    openweather_api_key: SecretStr | None = None
    openweather_url: str = "https://api.openweathermap.org/data/2.5/forecast"
    openweather_timeout_s: float = 5.0

    # Accounts (app.services.accounts): a log-in lasts this many days. The session cookie
    # is Secure only when asked: browsers drop Secure cookies over plain http, except on
    # localhost. Set SESSION_COOKIE_SECURE=true wherever the site is served over HTTPS.
    session_days: int = 30
    session_cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
