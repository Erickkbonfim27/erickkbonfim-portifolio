"""Scheduled jobs that run once even when several workers are up.

Each run takes a PostgreSQL advisory lock named after the job; a worker that
cannot get it skips the run. Every run that executes is recorded in
`platform_job_runs`, which the status page reads.
"""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from portfolio.platform.db import Base

log = logging.getLogger(__name__)

JobFn = Callable[[], Awaitable[str]]
"""A job returns a one-line summary of what it did, e.g. 'deleted 3 contacts'."""


class JobRunRow(Base):
    __tablename__ = "platform_job_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(80), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    detail: Mapped[str] = mapped_column(Text)


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    name: str
    hour: int
    minute: int
    run: JobFn


def lock_key(job: str) -> int:
    """A stable signed 64-bit key for pg_advisory_lock, derived from the job name."""
    return int.from_bytes(hashlib.sha256(job.encode()).digest()[:8], "big", signed=True)


async def run_exclusive(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    name: str,
    job: JobFn,
    now: Callable[[], datetime],
) -> bool:
    """Run `job` if no other worker is running it. Returns False when skipped."""
    key = {"key": lock_key(name)}
    async with engine.connect() as lock:
        if not await lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), key):
            return False
        try:
            started = now()
            try:
                detail, status = await job(), "ok"
            except Exception as error:
                log.exception("job failed", extra={"job": name})
                detail, status = repr(error)[:2000], "failed"
            async with session_factory() as session, session.begin():
                session.add(
                    JobRunRow(
                        id=uuid4(),
                        job=name,
                        started_at=started,
                        finished_at=now(),
                        status=status,
                        detail=detail,
                    )
                )
        finally:
            await lock.execute(text("SELECT pg_advisory_unlock(:key)"), key)
    return True
