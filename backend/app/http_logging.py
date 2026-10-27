"""Keep API keys that travel in query strings out of the logs."""

import logging

import httpx

# HERE takes its key as `apiKey`, OpenWeatherMap as `appid`.
SECRET_PARAMS = ("apiKey", "appid")


class HideApiKeys(logging.Filter):
    """httpx logs request URLs (at INFO level), API keys in the query included."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_redact(arg) for arg in record.args)
        return True


def _redact(arg: object) -> object:
    if not isinstance(arg, httpx.URL):
        return arg
    for name in SECRET_PARAMS:
        if name in arg.params:
            arg = arg.copy_set_param(name, "***")
    return arg


HIDE_API_KEYS = HideApiKeys()


def hide_api_keys() -> None:
    """Install the filter on httpx's logger; calling it again changes nothing."""
    logging.getLogger("httpx").addFilter(HIDE_API_KEYS)
