from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import aio_pika
import pytest

from portfolio.platform import messaging
from portfolio.platform.messaging import Delivery, QueueSpec, RabbitBroker, next_step

SPEC = QueueSpec(
    "contacts.notify", ("contact.received",), max_attempts=3, retry_delay=timedelta(seconds=5)
)


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[aio_pika.Message, str]] = []

    async def publish(self, message: aio_pika.Message, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeIncoming:
    def __init__(self, body: bytes, headers: dict[str, Any] | None = None) -> None:
        self.body = body
        self.headers = headers
        self.message_id = "event-1"
        self.routing_key = "contact.received"
        self.content_type = "application/json"
        self.acked = False

    async def ack(self) -> None:
        self.acked = True


class FakeQueue:
    def __init__(self, name: str, arguments: dict[str, Any] | None) -> None:
        self.name = name
        self.arguments = arguments
        self.bindings: list[str] = []
        self.messages: list[FakeIncoming] = []

    async def bind(self, exchange: FakeExchange, routing_key: str) -> None:
        self.bindings.append(routing_key)

    @asynccontextmanager
    async def iterator(self) -> AsyncIterator[AsyncIterator[FakeIncoming]]:
        async def messages() -> AsyncIterator[FakeIncoming]:
            for message in self.messages:
                yield message

        yield messages()


class FakeChannel:
    def __init__(self) -> None:
        self.exchange = FakeExchange()
        self.default_exchange = FakeExchange()
        self.queues: dict[str, FakeQueue] = {}
        self.prefetch: int | None = None
        self.pending: list[FakeIncoming] = []

    async def set_qos(self, prefetch_count: int) -> None:
        self.prefetch = prefetch_count

    async def declare_exchange(self, name: str, kind: str, durable: bool) -> FakeExchange:
        assert (name, kind, durable) == (messaging.EXCHANGE, aio_pika.ExchangeType.TOPIC, True)
        return self.exchange

    async def declare_queue(
        self, name: str, durable: bool, arguments: dict[str, Any] | None = None
    ) -> FakeQueue:
        assert durable
        queue = FakeQueue(name, arguments)
        if name == SPEC.name:
            queue.messages = self.pending
        self.queues[name] = queue
        return queue


class FakeConnection:
    def __init__(self) -> None:
        self.channel_ = FakeChannel()
        self.closed = False

    async def channel(self, publisher_confirms: bool) -> FakeChannel:
        assert publisher_confirms
        return self.channel_

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
async def broker(monkeypatch: pytest.MonkeyPatch) -> tuple[RabbitBroker, FakeConnection]:
    connection = FakeConnection()

    async def connect_robust(url: str) -> FakeConnection:
        assert url == "amqp://test"
        return connection

    monkeypatch.setattr("aio_pika.connect_robust", connect_robust)
    broker = RabbitBroker("amqp://test", prefetch=7)
    await broker.connect()
    return broker, connection


def test_next_step() -> None:
    assert [next_step(attempt, 3) for attempt in (1, 2, 3, 4)] == ["retry", "retry", "dlq", "dlq"]


async def test_must_connect_first() -> None:
    with pytest.raises(RuntimeError, match="connect"):
        await RabbitBroker("amqp://x").publish("t", b"{}", "id")
    await RabbitBroker("amqp://x").close()  # closing an unconnected broker is a no-op


async def test_publish_is_persistent_and_tagged(
    broker: tuple[RabbitBroker, FakeConnection],
) -> None:
    rabbit, connection = broker
    await rabbit.publish("contact.received", b'{"id": "1"}', "event-1")
    [(message, routing_key)] = connection.channel_.exchange.published
    assert routing_key == "contact.received"
    assert message.message_id == "event-1"
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.headers == {"x-attempt": 1, "x-topic": "contact.received"}
    assert connection.channel_.prefetch == 7
    await rabbit.close()
    assert connection.closed


async def test_topology(broker: tuple[RabbitBroker, FakeConnection]) -> None:
    rabbit, connection = broker
    await rabbit.declare(SPEC)
    queues = connection.channel_.queues
    assert queues[SPEC.name].bindings == ["contact.received"]
    assert queues[f"{SPEC.name}.retry"].arguments == {
        "x-message-ttl": 5000,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": SPEC.name,
    }
    assert f"{SPEC.name}.dlq" in queues


async def _consume(
    broker: tuple[RabbitBroker, FakeConnection], *messages: FakeIncoming, fail: bool = False
) -> list[Delivery]:
    rabbit, connection = broker
    connection.channel_.pending.extend(messages)
    seen: list[Delivery] = []

    async def handler(delivery: Delivery) -> None:
        seen.append(delivery)
        if fail:
            raise ValueError("boom")

    await rabbit.consume(SPEC, handler)
    return seen


async def test_success_acks(broker: tuple[RabbitBroker, FakeConnection]) -> None:
    message = FakeIncoming(b'{"id": "1"}', {"x-attempt": 2, "x-topic": "contact.received"})
    [delivery] = await _consume(broker, message)
    assert delivery == Delivery("event-1", "contact.received", {"id": "1"}, 2)
    assert message.acked
    assert broker[1].channel_.default_exchange.published == []


async def test_failure_goes_to_retry_then_dlq(broker: tuple[RabbitBroker, FakeConnection]) -> None:
    first = FakeIncoming(b'{"id": "1"}')  # no headers: attempt 1
    last = FakeIncoming(b'{"id": "1"}', {"x-attempt": 3, "x-topic": "contact.received"})
    await _consume(broker, first, last, fail=True)
    routed = broker[1].channel_.default_exchange.published
    assert [key for _, key in routed] == [f"{SPEC.name}.retry", f"{SPEC.name}.dlq"]
    retry, _ = routed[0]
    assert retry.headers is not None
    assert retry.headers["x-attempt"] == 2
    assert "boom" in str(retry.headers["x-last-error"])
    assert first.acked
    assert last.acked


async def test_malformed_json_is_routed_not_lost(
    broker: tuple[RabbitBroker, FakeConnection],
) -> None:
    message = FakeIncoming(b"not json", {"x-attempt": 3})
    assert await _consume(broker, message) == []
    [(_, key)] = broker[1].channel_.default_exchange.published
    assert key == f"{SPEC.name}.dlq"
