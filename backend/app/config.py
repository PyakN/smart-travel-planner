from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives at the repo root; commands usually run from backend/.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str
    default_city: str = "lisbon"

    llm_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    # Empty means the provider's default (see app.llm.factory).
    llm_model: str | None = None
    llm_fallback_model: str | None = None
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 2048
    llm_daily_token_budget: int = 1_000_000
    llm_cache_size: int = 256

    # Walking distances: OSRM foot routing (public FOSSGIS server by default), with a
    # haversine fallback when it is unavailable.
    routing_provider: Literal["osrm", "haversine"] = "osrm"
    osrm_base_url: str = "https://routing.openstreetmap.de/routed-foot"
    osrm_timeout_s: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
