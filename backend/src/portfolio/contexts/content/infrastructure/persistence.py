from collections.abc import Callable, Collection
from datetime import datetime
from types import MappingProxyType, TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from portfolio.contexts.content.domain.entry import Attachment, Entry, EntryDraft, Translation
from portfolio.contexts.content.domain.errors import (
    SingletonKindError,
    SlugTakenError,
    UnknownFileError,
)
from portfolio.contexts.content.domain.events import ContentEvent
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status
from portfolio.contexts.content.infrastructure.models import (
    AttachmentRow,
    EntryRow,
    EntrySkillRow,
    TranslationRow,
)
from portfolio.platform.outbox import add_event


def _to_entry(row: EntryRow) -> Entry:
    content = EntryDraft(
        slug=row.slug,
        translations=MappingProxyType(
            {
                Lang(t.lang): Translation(title=t.title, summary=t.summary, body=t.body)
                for t in row.translations
            }
        ),
        details=MappingProxyType(dict(row.details)),
        tags=tuple(row.tags),
        skills=tuple(s.skill_id for s in row.skills),
        attachments=tuple(Attachment(a.file_id, a.label) for a in row.attachments),
        position=row.position,
    )
    return Entry(
        id=row.id,
        kind=Kind(row.kind),
        status=Status(row.status),
        version=row.version,
        content=content,
        created_at=row.created_at,
        updated_at=row.updated_at,
        published_at=row.published_at,
    )


def _apply(row: EntryRow, entry: Entry) -> None:
    content = entry.content
    row.slug = content.slug
    row.status = entry.status.value
    row.version = entry.version
    row.details = dict(content.details)
    row.tags = list(content.tags)
    row.position = content.position
    row.updated_at = entry.updated_at
    row.published_at = entry.published_at
    row.translations = [
        TranslationRow(
            entry_id=entry.id, lang=lang.value, title=t.title, summary=t.summary, body=dict(t.body)
        )
        for lang, t in content.translations.items()
    ]
    row.skills = [
        EntrySkillRow(entry_id=entry.id, skill_id=skill, position=index)
        for index, skill in enumerate(content.skills)
    ]
    row.attachments = [
        AttachmentRow(entry_id=entry.id, file_id=a.file_id, label=a.label, position=index)
        for index, a in enumerate(content.attachments)
    ]


class SqlEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, entry_id: UUID, *, for_update: bool = False) -> Entry | None:
        statement = select(EntryRow).where(EntryRow.id == entry_id)
        if for_update:
            statement = statement.with_for_update(of=EntryRow)
        row = await self._session.scalar(statement)
        return _to_entry(row) if row is not None else None

    async def list(self, kind: Kind | None, status: Status | None) -> list[Entry]:
        statement = select(EntryRow).order_by(EntryRow.kind, EntryRow.position, EntryRow.created_at)
        if kind is not None:
            statement = statement.where(EntryRow.kind == kind.value)
        if status is not None:
            statement = statement.where(EntryRow.status == status.value)
        return [_to_entry(row) for row in await self._session.scalars(statement)]

    async def get_by_slug(self, kind: Kind, slug: str) -> Entry | None:
        row = await self._session.scalar(
            select(EntryRow).where(EntryRow.kind == kind.value, EntryRow.slug == slug)
        )
        return _to_entry(row) if row is not None else None

    async def slug_taken(self, kind: Kind, slug: str, exclude: UUID | None) -> bool:
        statement = select(EntryRow.id).where(EntryRow.kind == kind.value, EntryRow.slug == slug)
        if exclude is not None:
            statement = statement.where(EntryRow.id != exclude)
        return await self._session.scalar(statement.limit(1)) is not None

    async def count(self, kind: Kind) -> int:
        statement = select(func.count()).select_from(EntryRow).where(EntryRow.kind == kind.value)
        return int(await self._session.scalar(statement) or 0)

    async def existing_skills(self, ids: Collection[UUID]) -> set[UUID]:
        if not ids:
            return set()
        statement = select(EntryRow.id).where(
            EntryRow.id.in_(list(ids)), EntryRow.kind == Kind.SKILL.value
        )
        return set(await self._session.scalars(statement))

    async def add(self, entry: Entry) -> None:
        row = EntryRow(id=entry.id, kind=entry.kind.value, created_at=entry.created_at)
        _apply(row, entry)
        self._session.add(row)

    async def save(self, entry: Entry) -> None:
        _apply(await self._session.get_one(EntryRow, entry.id), entry)

    async def delete(self, entry_id: UUID) -> None:
        await self._session.execute(delete(EntryRow).where(EntryRow.id == entry_id))


# Constraint name -> the domain error it means. Races the use case checks could miss.
_CONSTRAINT_ERRORS: dict[str, type[Exception]] = {
    "fk_content_attachments_file_id_files_objects": UnknownFileError,
    "uq_content_entries_kind": SlugTakenError,
    "uq_content_entries_singleton": SingletonKindError,
}


def _translate(error: IntegrityError) -> Exception | None:
    constraint = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    constraint = constraint or getattr(error.orig, "constraint_name", None)
    for name, domain_error in _CONSTRAINT_ERRORS.items():
        if constraint == name or name in str(error.orig):
            return domain_error(name)
    return None


class SqlContentUnitOfWork:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], now: Callable[[], datetime]
    ) -> None:
        self._session_factory = session_factory
        self._now = now

    @property
    def entries(self) -> SqlEntryRepository:
        return self._entries

    def record(self, event: ContentEvent) -> None:
        self._events.append(event)

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._entries = SqlEntryRepository(self._session)
        self._events: list[ContentEvent] = []
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._session.close()

    async def commit(self) -> None:
        now = self._now()
        for event in self._events:
            add_event(self._session, event.topic, event.payload, now)
        self._events.clear()
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            translated = _translate(error)
            if translated is None:
                raise
            raise translated from error
