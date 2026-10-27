import logging

import httpx
import pytest

from app.http_logging import HIDE_API_KEYS, hide_api_keys


@pytest.mark.parametrize("param", ["apiKey", "appid"])
def test_keys_in_logged_urls_are_hidden(param: str, caplog: pytest.LogCaptureFixture) -> None:
    hide_api_keys()
    hide_api_keys()  # idempotent
    assert logging.getLogger("httpx").filters.count(HIDE_API_KEYS) == 1
    url = httpx.URL("https://api.test/v1", params={"q": "lisbon", param: "secret-key"})
    with caplog.at_level(logging.INFO, logger="httpx"):
        # How httpx logs a request.
        logging.getLogger("httpx").info('HTTP Request: %s %s "%s"', "GET", url, "HTTP/1.1 200 OK")
    assert "secret-key" not in caplog.text
    assert f"{param}=%2A%2A%2A" in caplog.text
    assert "q=lisbon" in caplog.text
