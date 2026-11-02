"""Pure parts of the platform. The database-backed parts are integration tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from portfolio import worker
from portfolio.platform.jobs import ScheduledJob, lock_key
from portfolio.platform.outbox import OutboxRow, add_event
from portfolio.platform.ratelimit import keyed_hash, window_start
from tests.unit.identity.fakes import START


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, row: Any) -> None:
        self.added.append(row)


def test_add_event_writes_an_unpublished_row() -> None:
    session = RecordingSession()
    event_id = add_event(session, "contact.received", {"id": "1"}, START)  # type: ignore[arg-type]
    [row] = session.added
    assert isinstance(row, OutboxRow)
    assert (row.id, row.topic, row.payload, row.created_at, row.published_at, row.attempts) == (
        event_id,
        "contact.received",
        {"id": "1"},
        START,
        None,
        0,
    )


def test_windows_align_to_utc_days_and_hours() -> None:
    now = datetime(2026, 11, 2, 15, 47, tzinfo=UTC)
    assert window_start(now, timedelta(days=1)) == datetime(2026, 11, 2, tzinfo=UTC)
    assert window_start(now, timedelta(hours=1)) == datetime(2026, 11, 2, 15, tzinfo=UTC)


def test_keyed_hash_hides_the_value_and_depends_on_the_secret() -> None:
    assert keyed_hash("s1", "1.2.3.4") == keyed_hash("s1", "1.2.3.4")
    assert keyed_hash("s1", "1.2.3.4") != keyed_hash("s2", "1.2.3.4")
    assert "1.2.3.4" not in keyed_hash("s1", "1.2.3.4")


def test_lock_keys_are_stable_signed_64_bit() -> None:
    key = lock_key("purge-expired-contacts")
    assert key == lock_key("purge-expired-contacts")
    assert key != lock_key("housekeeping")
    assert -(2**63) <= key < 2**63


def test_worker_settings_are_required() -> None:
    assert worker._require("amqp://x", "RABBITMQ_URL") == "amqp://x"
    with pytest.raises(worker.MissingWorkerSettingError, match="RESEND_API_KEY"):
        worker._require(None, "RESEND_API_KEY")


class FakeInfra:
    engine = object()
    session_factory = object()

    class clock:  # noqa: N801 - mimics the attribute of Infrastructure
        @staticmethod
        def now() -> datetime:
            return START


def test_daily_jobs_are_scheduled_in_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_run_exclusive(engine: object, factory: object, name: str, *_: object) -> bool:
        calls.append(name)
        return True

    monkeypatch.setattr(worker, "run_exclusive", fake_run_exclusive)

    async def job() -> str:
        return "done"

    jobs = [ScheduledJob("a", 3, 0, job), ScheduledJob("b", 3, 30, job)]
    scheduler = worker.schedule(FakeInfra(), jobs)  # type: ignore[arg-type]
    scheduled = scheduler.get_jobs()
    assert [str(j.trigger) for j in scheduled] == [
        "cron[hour='3', minute='0']",
        "cron[hour='3', minute='30']",
    ]
    for scheduled_job in scheduled:
        asyncio.run(scheduled_job.func())
    assert calls == ["a", "b"]


def test_daily_job_names(monkeypatch: pytest.MonkeyPatch) -> None:
    infra = FakeInfra()
    jobs = worker.daily_jobs(infra)  # type: ignore[arg-type]
    assert [(j.name, j.hour, j.minute) for j in jobs] == [
        ("purge-expired-contacts", 3, 0),
        ("housekeeping", 3, 30),
    ]


async def test_relay_sleeps_only_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    results = iter([2, 0])
    sleeps: list[float] = []

    async def fake_relay(*_: object) -> int:
        try:
            return next(results)
        except StopIteration:
            raise asyncio.CancelledError from None

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(worker, "relay_once", fake_relay)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker.relay_forever(FakeInfra(), broker=object())  # type: ignore[arg-type]
    assert sleeps == [worker.RELAY_IDLE]
