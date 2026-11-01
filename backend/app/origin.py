"""Only requests that came through the frontend's proxy, once ORIGIN_SECRET is set.

Deployed behind Vercel, the API still answers at its own address, where a caller can claim
any X-Forwarded-For and so be any number of clients to the per-client limits
(app.rate_limit). The frontend's proxy sends the shared secret in a header that the
browser cannot set for it (frontend/src/proxy.ts), and requests without it get 403.
/health stays open for the host's health checks. Without ORIGIN_SECRET every request is
let through, as in development and behind the Caddy edge (docker-compose.prod.yml).
"""

import hmac
from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

ORIGIN_SECRET_HEADER = b"x-origin-secret"
OPEN_PATHS = frozenset({"/health"})


class OriginGuard:
    """ASGI middleware: 403 for requests without the secret, while `secret()` gives one."""

    def __init__(self, app: ASGIApp, secret: Callable[[], str | None]) -> None:
        self.app = app
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        expected = self.secret()
        if scope["type"] != "http" or not expected or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        sent = next((v for k, v in scope["headers"] if k == ORIGIN_SECRET_HEADER), b"")
        if hmac.compare_digest(sent, expected.encode()):
            await self.app(scope, receive, send)
            return
        response = JSONResponse({"detail": "Requests go through the website."}, status_code=403)
        await response(scope, receive, send)
