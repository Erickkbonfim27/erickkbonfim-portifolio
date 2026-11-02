"""Fixed-window rate limiting stored in PostgreSQL.

Used for limits counted in hours or days (contact form, chat quota), where the
counter must survive restarts and be shared by every worker. Keys are HMACs, so
the table never holds a raw IP or email address.
"""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from portfolio.platform.db import Base


class RateLimitRow(Base):
    __tablename__ = "platform_rate_limits"

    bucket: Mapped[str] = mapped_column(String(40), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer)


def window_start(now: datetime, window: timedelta) -> datetime:
    """Windows aligned to the Unix epoch, so a 1-day window is a UTC calendar day."""
    seconds = window.total_seconds()
    timestamp = now.timestamp()
    return datetime.fromtimestamp(timestamp - timestamp % seconds, tz=UTC)


def keyed_hash(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


class PostgresRateLimiter:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        secret: str,
        now: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._secret = secret
        self._now = now

    async def hit(self, bucket: str, key: str, limit: int, window: timedelta) -> bool:
        """Count one hit; True while the count is within `limit` for the current window."""
        statement = (
            insert(RateLimitRow)
            .values(
                bucket=bucket,
                key_hash=keyed_hash(self._secret, key),
                window_start=window_start(self._now(), window),
                hits=1,
            )
            .on_conflict_do_update(
                index_elements=["bucket", "key_hash", "window_start"],
                set_={"hits": RateLimitRow.hits + 1},
            )
            .returning(RateLimitRow.hits)
        )
        async with self._session_factory() as session, session.begin():
            hits = await session.scalar(statement)
        return hits is not None and hits <= limit

    async def purge(self, before: datetime) -> int:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                delete(RateLimitRow).where(RateLimitRow.window_start < before)
            )
        return int(getattr(result, "rowcount", 0) or 0)
