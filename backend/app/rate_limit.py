"""Per-client limits on the endpoints that call the LLM.

Each call costs tokens and holds a worker for seconds, so a client may make only so many in
a short window (a script hammering the planner) and in a day (one client spending the
daily token budget, app.llm.service.TokenBudget, that every user shares). Clients are told
apart by their address. Kept in memory: per process and forgotten on restart, like the
token budget and the log-in limit.

Behind a proxy the address is the proxy's, unless uvicorn trusts it to name the client
(`--forwarded-allow-ips`, 127.0.0.1 by default: the Next.js proxy on the same host).
"""

import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    requests: int
    window_s: float


class RateLimitedError(Exception):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"rate limited for {retry_after_s} s")
        self.retry_after_s = retry_after_s


class RateLimiter:
    """At most `requests` per `window_s` for each limit, per key (a sliding window). Every
    request counts, refused ones excepted. The keys not seen for longest are forgotten
    beyond `max_keys`."""

    def __init__(
        self,
        limits: Sequence[Limit],
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limits = [limit for limit in limits if limit.requests > 0]
        self.clock = clock
        self.max_keys = max_keys
        self._longest = max((limit.window_s for limit in self.limits), default=0.0)
        self._keep = max((limit.requests for limit in self.limits), default=0)
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def hit(self, key: str) -> None:
        """Count a request; RateLimitedError if `key` has to wait."""
        if not self.limits:
            return
        now = self.clock()
        hits = self._hits.pop(key, deque())
        while hits and hits[0] <= now - self._longest:
            hits.popleft()
        self._hits[key] = hits  # most recently seen last
        wait = max(
            (
                hits[-limit.requests] + limit.window_s - now
                for limit in self.limits
                if len(hits) >= limit.requests and hits[-limit.requests] > now - limit.window_s
            ),
            default=0.0,
        )
        if wait > 0:
            raise RateLimitedError(max(1, math.ceil(wait)))
        hits.append(now)
        while len(hits) > self._keep:  # older hits decide nothing
            hits.popleft()
        while len(self._hits) > self.max_keys:
            self._hits.popitem(last=False)


def describe_wait(seconds: int) -> str:
    """How long a refused client waits: "40 s", "3 min", "5 h"."""
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{math.ceil(seconds / 60)} min"
    return f"{math.ceil(seconds / 3600)} h"
