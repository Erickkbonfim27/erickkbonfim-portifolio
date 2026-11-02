"""Transactional outbox.

Contexts write events with `add_event` inside the same database transaction as
the change that caused them. The worker's relay later publishes them to RabbitMQ.
Either both the change and its event are committed, or neither is: no dual write.
"""

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from portfolio.platform.db import Base

log = logging.getLogger(__name__)


class OutboxRow(Base):
    __tablename__ = "platform_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


def add_event(session: AsyncSession, topic: str, payload: Mapping[str, Any], now: datetime) -> UUID:
    event_id = uuid4()
    session.add(
        OutboxRow(id=event_id, topic=topic, payload=dict(payload), created_at=now, attempts=0)
    )
    return event_id


class Publisher(Protocol):
    async def publish(self, topic: str, body: bytes, message_id: str) -> None:
        """Returns only once the broker confirmed the message."""
        ...


async def relay_once(
    session_factory: async_sessionmaker[AsyncSession],
    publisher: Publisher,
    now: datetime,
    batch_size: int = 50,
) -> int:
    """Publish one batch of pending events, oldest first. Returns how many were sent.

    `FOR UPDATE SKIP LOCKED` lets several relays run without sending the same row
    twice. Delivery is at-least-once (a crash between publish and commit resends),
    which is why every consumer is idempotent.
    """
    async with session_factory() as session, session.begin():
        rows = (
            await session.scalars(
                select(OutboxRow)
                .where(OutboxRow.published_at.is_(None))
                .order_by(OutboxRow.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        sent = 0
        for row in rows:
            try:
                await publisher.publish(row.topic, json.dumps(row.payload).encode(), str(row.id))
            except Exception as error:
                row.attempts += 1
                row.last_error = repr(error)[:2000]
                log.warning("outbox publish failed", extra={"event_id": str(row.id)})
                break
            row.published_at = now
            sent += 1
        return sent
