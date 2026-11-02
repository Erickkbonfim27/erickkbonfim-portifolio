"""Per-IP request throttling for the whole API (token bucket, in memory).

Per-second limits must be cheap, so they live in process memory: with one
uvicorn worker that is exact; with several, each worker allows the rate on its
own. Limits counted in days (contact form, chat quota) are in PostgreSQL
instead (`ratelimit.py`), where they survive restarts.
"""

import json
import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

# Refill is computed in floating point; a client that waits exactly the advertised
# Retry-After must not be refused by a rounding error.
_EPSILON = 1e-9


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBuckets:
    def __init__(
        self,
        rate: float,
        burst: int,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._max_keys = max_keys
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    def take(self, key: str) -> float:
        """Spend one token. Returns 0 when allowed, else seconds until the next token."""
        now = self._clock()
        bucket = self._buckets.pop(key, None) or _Bucket(float(self._burst), now)
        bucket.tokens = min(self._burst, bucket.tokens + (now - bucket.updated) * self._rate)
        bucket.updated = now
        self._buckets[key] = bucket  # most recently used last
        if len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)  # forget the least recently seen client
        if bucket.tokens >= 1 - _EPSILON:
            bucket.tokens = max(0.0, bucket.tokens - 1)
            return 0.0
        return (1 - bucket.tokens) / self._rate


class ThrottleMiddleware:
    def __init__(
        self, app: ASGIApp, buckets: TokenBuckets, exempt_prefixes: tuple[str, ...] = ("/health",)
    ) -> None:
        self._app = app
        self._buckets = buckets
        self._exempt = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or str(scope["path"]).startswith(self._exempt):
            await self._app(scope, receive, send)
            return
        client = scope.get("client")
        wait = self._buckets.take(client[0] if client else "unknown")
        if wait == 0:
            await self._app(scope, receive, send)
            return
        body = json.dumps({"detail": "too many requests"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(max(1, math.ceil(wait))).encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
