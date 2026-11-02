"""RabbitMQ topology, publishing and consuming (aio-pika).

One topic exchange, `portfolio.events`. Each consumer owns a queue plus two helpers:

    <queue>.retry   holds a failed message for `retry_delay`, then dead-letters it
                    straight back to <queue> (default exchange, routing key = queue name,
                    so other consumers of the same topic never see the retry)
    <queue>.dlq     where a message lands after `max_attempts`; inspected by hand

Handlers must be idempotent: delivery is at-least-once.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

log = logging.getLogger(__name__)

EXCHANGE = "portfolio.events"
ATTEMPT_HEADER = "x-attempt"
TOPIC_HEADER = "x-topic"


@dataclass(frozen=True, slots=True)
class QueueSpec:
    name: str
    bindings: tuple[str, ...]
    max_attempts: int = 5
    retry_delay: timedelta = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class Delivery:
    message_id: str
    topic: str
    payload: dict[str, Any]
    attempt: int


Handler = Callable[[Delivery], Awaitable[None]]


def next_step(attempt: int, max_attempts: int) -> Literal["retry", "dlq"]:
    """Where a message goes when its handler failed on `attempt` (1-based)."""
    return "retry" if attempt < max_attempts else "dlq"


class RabbitBroker:
    def __init__(self, url: str, prefetch: int = 10) -> None:
        self._url = url
        self._prefetch = prefetch
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        # Publisher confirms: publish() returns only after the broker accepted the message.
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=self._prefetch)
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    @property
    def _ready(self) -> tuple[AbstractChannel, AbstractExchange]:
        if self._channel is None or self._exchange is None:
            raise RuntimeError("RabbitBroker.connect() was not awaited")
        return self._channel, self._exchange

    async def publish(self, topic: str, body: bytes, message_id: str) -> None:
        _, exchange = self._ready
        await exchange.publish(
            aio_pika.Message(
                body,
                message_id=message_id,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={ATTEMPT_HEADER: 1, TOPIC_HEADER: topic},
            ),
            routing_key=topic,
        )

    async def declare(self, spec: QueueSpec) -> AbstractQueue:
        channel, exchange = self._ready
        queue = await channel.declare_queue(spec.name, durable=True)
        for binding in spec.bindings:
            await queue.bind(exchange, routing_key=binding)
        await channel.declare_queue(
            f"{spec.name}.retry",
            durable=True,
            arguments={
                "x-message-ttl": int(spec.retry_delay.total_seconds() * 1000),
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": spec.name,
            },
        )
        await channel.declare_queue(f"{spec.name}.dlq", durable=True)
        return queue

    async def consume(self, spec: QueueSpec, handler: Handler) -> None:
        """Consume until cancelled."""
        queue = await self.declare(spec)
        async with queue.iterator() as messages:
            async for message in messages:
                await self._handle(spec, message, handler)

    async def _handle(
        self, spec: QueueSpec, message: AbstractIncomingMessage, handler: Handler
    ) -> None:
        headers = message.headers or {}
        attempt = int(str(headers.get(ATTEMPT_HEADER, 1)))
        topic = str(headers.get(TOPIC_HEADER, message.routing_key or ""))
        try:
            payload = json.loads(message.body)
            await handler(Delivery(message.message_id or "", topic, payload, attempt))
        except Exception as error:
            step = next_step(attempt, spec.max_attempts)
            log.warning(
                "message handler failed",
                extra={"queue": spec.name, "message_id": message.message_id, "step": step},
            )
            channel, _ = self._ready
            await channel.default_exchange.publish(
                aio_pika.Message(
                    message.body,
                    message_id=message.message_id,
                    content_type=message.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={
                        ATTEMPT_HEADER: attempt + 1,
                        TOPIC_HEADER: topic,
                        "x-last-error": repr(error)[:500],
                    },
                ),
                routing_key=f"{spec.name}.{step}",
            )
        await message.ack()
