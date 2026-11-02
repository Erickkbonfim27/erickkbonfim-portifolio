from httpx import ASGITransport, AsyncClient
from starlette.types import Receive, Scope, Send

from portfolio.platform.throttle import ThrottleMiddleware, TokenBuckets


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_burst_then_steady_rate() -> None:
    clock = Clock()
    buckets = TokenBuckets(rate=10, burst=3, clock=clock)
    assert [buckets.take("ip") for _ in range(3)] == [0, 0, 0]
    assert buckets.take("ip") == 0.1  # next token in 1/rate seconds
    clock.now += 0.05
    assert round(buckets.take("ip"), 9) == 0.05
    clock.now += 0.05
    assert buckets.take("ip") == 0  # waited exactly the advertised time
    assert buckets.take("other") == 0  # buckets are per client


def test_tokens_refill_up_to_the_burst_only() -> None:
    clock = Clock()
    buckets = TokenBuckets(rate=10, burst=2, clock=clock)
    buckets.take("ip")
    clock.now += 60
    assert [buckets.take("ip") for _ in range(3)][-1] > 0


def test_forgets_the_least_recent_clients() -> None:
    clock = Clock()
    buckets = TokenBuckets(rate=1, burst=1, max_keys=2, clock=clock)
    buckets.take("a")
    buckets.take("b")
    buckets.take("c")  # evicts "a"
    assert buckets.take("a") == 0  # a fresh bucket again
    assert buckets.take("c") > 0


async def ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def test_middleware_answers_429_with_retry_after() -> None:
    app = ThrottleMiddleware(ok_app, TokenBuckets(rate=1, burst=1, clock=Clock()))
    async with AsyncClient(transport=ASGITransport(app), base_url="https://a.t") as client:
        assert (await client.get("/api/profile")).status_code == 200
        throttled = await client.get("/api/profile")
        assert throttled.status_code == 429
        assert throttled.headers["retry-after"] == "1"
        assert throttled.json() == {"detail": "too many requests"}
        assert (await client.get("/health/live")).status_code == 200  # exempt


async def test_unknown_client_and_lifespan_pass_through() -> None:
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    middleware = ThrottleMiddleware(app, TokenBuckets(rate=1, burst=1, clock=Clock()))

    async def receive() -> dict[str, object]:
        return {}

    async def send(message: dict[str, object]) -> None:
        return None

    await middleware({"type": "lifespan"}, receive, send)  # type: ignore[arg-type]
    await middleware({"type": "http", "path": "/api/x", "client": None}, receive, send)  # type: ignore[arg-type]
    assert seen == ["lifespan", "http"]
