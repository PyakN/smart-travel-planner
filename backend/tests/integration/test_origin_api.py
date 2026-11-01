import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

SECRET = "a-long-random-value"


def test_the_api_answers_only_requests_with_the_origin_secret(database_url: str) -> None:
    with pytest.MonkeyPatch.context() as env:
        env.setenv("ORIGIN_SECRET", SECRET)
        get_settings.cache_clear()
        with TestClient(create_app()) as client:
            refused = client.get("/cities")
            assert refused.status_code == 403
            assert refused.headers["X-Request-ID"]  # still logged with its request id
            assert client.get("/cities", headers={"X-Origin-Secret": SECRET}).status_code == 200
            assert client.get("/health").status_code == 200
    get_settings.cache_clear()
