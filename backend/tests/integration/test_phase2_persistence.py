"""Content, files, contacts and platform adapters against a real PostgreSQL."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from portfolio import worker
from portfolio.contexts.contacts.domain.model import (
    ContactForm,
    ContactRequest,
    ContactStatus,
    DuplicateSubmissionError,
)
from portfolio.contexts.contacts.infrastructure.persistence import SqlContactsUnitOfWork
from portfolio.contexts.content.domain.entry import Attachment, Entry, EntryDraft, Translation
from portfolio.contexts.content.domain.errors import (
    SingletonKindError,
    SlugTakenError,
    UnknownFileError,
)
from portfolio.contexts.content.domain.events import entry_published
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status
from portfolio.contexts.content.infrastructure.persistence import SqlContentUnitOfWork
from portfolio.contexts.files.domain.model import FileInUseError, StoredFile
from portfolio.contexts.files.infrastructure.persistence import SqlFilesUnitOfWork
from portfolio.platform.jobs import JobRunRow, lock_key, run_exclusive
from portfolio.platform.outbox import OutboxRow, relay_once
from portfolio.platform.ratelimit import PostgresRateLimiter
from tests.unit.identity.fakes import START

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
BOTH = {Lang.EN: Translation.create("Title", "S"), Lang.PT: Translation.create("Título", "R")}


def _entry(kind: Kind = Kind.EXPERIENCE, slug: str = "loopia", **extra: object) -> Entry:
    details = {
        Kind.EXPERIENCE: {"organization": "Loopia", "start": "2026-05"},
        Kind.SKILL: {"category": "ai"},
        Kind.PROFILE: {"name": "Erick", "availability": "open"},
    }[kind]
    draft = EntryDraft.build(kind, slug=slug, translations=BOTH, details=details, **extra)  # type: ignore[arg-type]
    return Entry.new(uuid4(), kind, draft, START)


def _file() -> StoredFile:
    file_id = uuid4()
    return StoredFile(file_id, f"{file_id}.pdf", "cv.pdf", "application/pdf", 10, "0" * 64, START)


def content(factory: Factory) -> SqlContentUnitOfWork:
    return SqlContentUnitOfWork(factory, lambda: START)


async def test_entry_round_trip_with_children(session_factory: Factory) -> None:
    stored = _file()
    async with SqlFilesUnitOfWork(session_factory) as uow:
        await uow.files.add(stored)
        await uow.commit()
    python = _entry(Kind.SKILL, "python")
    entry = _entry(skills=[python.id], attachments=[Attachment(stored.id, "CV")], tags=["ai"])
    async with content(session_factory) as uow:
        await uow.entries.add(python)
        await uow.entries.add(entry)
        await uow.commit()
    async with content(session_factory) as uow:
        loaded = await uow.entries.get(entry.id, for_update=True)
        assert loaded == entry
        assert await uow.entries.existing_skills({python.id, entry.id}) == {python.id}
        assert await uow.entries.existing_skills(set()) == set()
        assert await uow.entries.slug_taken(Kind.EXPERIENCE, "loopia", None)
        assert not await uow.entries.slug_taken(Kind.EXPERIENCE, "loopia", entry.id)
        assert await uow.entries.count(Kind.SKILL) == 1
        assert [e.id for e in await uow.entries.list(Kind.EXPERIENCE, Status.DRAFT)] == [entry.id]
        assert await uow.entries.list(None, Status.PUBLISHED) == []


async def test_save_replaces_children_and_events_go_to_the_outbox(
    session_factory: Factory,
) -> None:
    entry = _entry(tags=["a"])
    async with content(session_factory) as uow:
        await uow.entries.add(entry)
        await uow.commit()
    edited = entry.edited(
        EntryDraft.build(
            Kind.EXPERIENCE,
            slug="loopia",
            translations=BOTH,
            details={"organization": "Loopia", "start": "2026-05"},
            tags=["b"],
        ),
        START,
    ).published(START)
    async with content(session_factory) as uow:
        await uow.entries.save(edited)
        uow.record(entry_published(edited))
        await uow.commit()
    async with session_factory() as session:
        topics = (await session.scalars(select(OutboxRow.topic))).all()
    assert topics == ["content.entry.published"]
    async with content(session_factory) as uow:
        loaded = await uow.entries.get(entry.id)
        assert loaded is not None
        assert (loaded.content.tags, loaded.status) == (("b",), Status.PUBLISHED)
        await uow.entries.delete(entry.id)
        await uow.commit()
    async with content(session_factory) as uow:
        assert await uow.entries.get(entry.id) is None


@pytest.mark.parametrize(
    ("first", "second", "error"),
    [
        (("loopia",), ("loopia",), SlugTakenError),
        (("erick", Kind.PROFILE), ("erick-2", Kind.PROFILE), SingletonKindError),
    ],
)
async def test_constraints_become_domain_errors(
    session_factory: Factory,
    first: tuple[object, ...],
    second: tuple[object, ...],
    error: type[Exception],
) -> None:
    def build(args: tuple[object, ...]) -> Entry:
        slug = str(args[0])
        kind = args[1] if len(args) > 1 else Kind.EXPERIENCE
        return _entry(kind, slug)  # type: ignore[arg-type]

    async with content(session_factory) as uow:
        await uow.entries.add(build(first))
        await uow.commit()
    async with content(session_factory) as uow:
        await uow.entries.add(build(second))
        with pytest.raises(error):
            await uow.commit()


async def test_attachment_foreign_key(session_factory: Factory) -> None:
    async with content(session_factory) as uow:
        await uow.entries.add(_entry(attachments=[Attachment(uuid4(), "CV")]))
        with pytest.raises(UnknownFileError):
            await uow.commit()
    stored = _file()
    async with SqlFilesUnitOfWork(session_factory) as uow:
        await uow.files.add(stored)
        await uow.commit()
    async with content(session_factory) as uow:
        await uow.entries.add(_entry(attachments=[Attachment(stored.id, "CV")]))
        await uow.commit()
    async with SqlFilesUnitOfWork(session_factory) as uow:
        assert await uow.files.get(stored.id) == stored
        assert [f.id for f in await uow.files.list()] == [stored.id]
        assert await uow.files.find_by_sha256(stored.sha256) == stored
        assert await uow.files.find_by_sha256("0" * 64) is None
        await uow.files.delete(stored.id)
        with pytest.raises(FileInUseError):
            await uow.commit()


async def test_contacts_repository(session_factory: Factory) -> None:
    form = ContactForm.build("Ana", " Ana@Corp.dev ", "AI Engineer role", None, "en")
    request = ContactRequest(uuid4(), form, ContactStatus.NEW, "key-1", START)
    uow = SqlContactsUnitOfWork(session_factory, lambda: START)
    async with uow:
        await uow.contacts.add(request)
        uow.record("contact.received", {"id": str(request.id)})
        await uow.commit()
    async with SqlContactsUnitOfWork(session_factory, lambda: START) as uow:
        assert await uow.contacts.get(request.id) == request
        assert await uow.contacts.get_by_idempotency_key("key-1") == request
        assert not await uow.contacts.thanked_since("ana@corp.dev", START)
        await uow.contacts.save(request.thanked(START).with_status(ContactStatus.READ))
        await uow.commit()
    async with SqlContactsUnitOfWork(session_factory, lambda: START) as uow:
        assert await uow.contacts.thanked_since("ana@corp.dev", START - timedelta(hours=1))
        assert [c.id for c in await uow.contacts.list(ContactStatus.READ)] == [request.id]
        assert await uow.contacts.list(ContactStatus.NEW) == []
        duplicate = ContactRequest(uuid4(), form, ContactStatus.NEW, "key-1", START)
        await uow.contacts.add(duplicate)
        with pytest.raises(DuplicateSubmissionError):
            await uow.commit()
    async with SqlContactsUnitOfWork(session_factory, lambda: START) as uow:
        assert await uow.contacts.delete_created_before(START + timedelta(seconds=1)) == 1
        await uow.contacts.delete(uuid4())
        await uow.commit()


class Publisher:
    def __init__(self, fail_on: int | None = None) -> None:
        self.sent: list[tuple[str, bytes, str]] = []
        self.fail_on = fail_on

    async def publish(self, topic: str, body: bytes, message_id: str) -> None:
        if self.fail_on is not None and len(self.sent) == self.fail_on:
            raise ConnectionError("broker down")
        self.sent.append((topic, body, message_id))


async def test_outbox_relay_in_order_and_stops_on_failure(session_factory: Factory) -> None:
    async with SqlContactsUnitOfWork(session_factory, lambda: START) as uow:
        uow.record("a", {"n": 1})
        await uow.commit()
    async with SqlContactsUnitOfWork(session_factory, lambda: START + timedelta(seconds=1)) as uow:
        uow.record("b", {"n": 2})
        await uow.commit()
    failing = Publisher(fail_on=1)
    assert await relay_once(session_factory, failing, START) == 1
    assert [topic for topic, _, _ in failing.sent] == ["a"]
    healthy = Publisher()
    assert await relay_once(session_factory, healthy, START) == 1
    assert [topic for topic, _, _ in healthy.sent] == ["b"]
    assert await relay_once(session_factory, healthy, START) == 0
    async with session_factory() as session:
        failed = await session.scalar(select(OutboxRow).where(OutboxRow.topic == "b"))
        assert failed is not None
        assert failed.attempts == 1
        assert "broker down" in (failed.last_error or "")


async def test_rate_limiter(session_factory: Factory) -> None:
    clock = [START]
    limiter = PostgresRateLimiter(session_factory, "s" * 32, lambda: clock[0])
    assert [await limiter.hit("contact", "1.2.3.4", 2, timedelta(days=1)) for _ in range(3)] == [
        True,
        True,
        False,
    ]
    assert await limiter.hit("contact", "5.6.7.8", 2, timedelta(days=1))
    clock[0] = START + timedelta(days=1)
    assert await limiter.hit("contact", "1.2.3.4", 2, timedelta(days=1))
    assert await limiter.purge(START + timedelta(hours=1)) == 2


async def test_jobs_run_once_and_are_recorded(
    engine: AsyncEngine, session_factory: Factory
) -> None:
    async def ok() -> str:
        return "did it"

    async def boom() -> str:
        raise ValueError("nope")

    assert await run_exclusive(engine, session_factory, "job-ok", ok, lambda: START)
    assert await run_exclusive(engine, session_factory, "job-fail", boom, lambda: START)

    async with engine.connect() as holder:
        await holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": lock_key("job-ok")})
        assert not await run_exclusive(engine, session_factory, "job-ok", ok, lambda: START)
        await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key("job-ok")})

    async with session_factory() as session:
        runs = (
            await session.execute(select(JobRunRow.job, JobRunRow.status, JobRunRow.detail))
        ).all()
        count = await session.scalar(select(func.count()).select_from(JobRunRow))
    assert count == 2
    assert ("job-ok", "ok", "did it") in runs
    assert any(
        job == "job-fail" and status == "failed" and "nope" in detail
        for job, status, detail in runs
    )


async def test_housekeeping_deletes_old_windows_and_sent_events(session_factory: Factory) -> None:
    later = START + timedelta(days=40)

    class Clock:
        @staticmethod
        def now() -> datetime:
            return later

    class Infra:
        clock = Clock()
        limiter = PostgresRateLimiter(session_factory, "s" * 32, lambda: START)

    Infra.session_factory = session_factory  # type: ignore[attr-defined]
    await Infra.limiter.hit("contact", "1.2.3.4", 5, timedelta(days=1))
    async with SqlContactsUnitOfWork(session_factory, lambda: START) as uow:
        uow.record("old", {})
        await uow.commit()
    assert await relay_once(session_factory, Publisher(), START) == 1
    summary = await worker.housekeeping(Infra())()  # type: ignore[arg-type]
    assert summary == "deleted 1 rate-limit windows and 1 sent events"


async def test_lookups_used_by_the_public_catalog(session_factory: Factory) -> None:
    stored = _file()
    async with SqlFilesUnitOfWork(session_factory) as uow:
        await uow.files.add(stored)
        await uow.commit()
    async with SqlFilesUnitOfWork(session_factory) as uow:
        assert await uow.files.get_many([stored.id, uuid4()]) == [stored]
    entry = _entry()
    async with content(session_factory) as uow:
        await uow.entries.add(entry)
        await uow.commit()
    async with content(session_factory) as uow:
        assert await uow.entries.get_by_slug(Kind.EXPERIENCE, "loopia") == entry
        assert await uow.entries.get_by_slug(Kind.PROJECT, "loopia") is None
