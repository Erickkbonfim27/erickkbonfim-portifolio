from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from portfolio.contexts.content.application.ports import Clock, ContentUnitOfWork
from portfolio.contexts.content.domain.entry import Entry, EntryDraft
from portfolio.contexts.content.domain.errors import (
    EntryNotFoundError,
    SingletonKindError,
    SlugTakenError,
    UnknownSkillError,
    VersionConflictError,
)
from portfolio.contexts.content.domain.events import (
    entry_deleted,
    entry_published,
    entry_unpublished,
)
from portfolio.contexts.content.domain.kinds import SINGLETON_KINDS, Kind, Status

UnitOfWorkFactory = Callable[[], ContentUnitOfWork]


async def _check_references(
    uow: ContentUnitOfWork, kind: Kind, draft: EntryDraft, exclude: UUID | None
) -> None:
    if await uow.entries.slug_taken(kind, draft.slug, exclude):
        raise SlugTakenError(f"{kind}/{draft.slug} already exists")
    missing = set(draft.skills) - await uow.entries.existing_skills(draft.skills)
    if missing:
        raise UnknownSkillError(f"not skill entries: {sorted(map(str, missing))}")


async def _load(uow: ContentUnitOfWork, entry_id: UUID, expected_version: int | None) -> Entry:
    entry = await uow.entries.get(entry_id, for_update=True)
    if entry is None:
        raise EntryNotFoundError(entry_id)
    if expected_version is not None and entry.version != expected_version:
        raise VersionConflictError(entry.version)
    return entry


@dataclass(frozen=True, slots=True)
class CreateEntry:
    uow: UnitOfWorkFactory
    clock: Clock

    async def __call__(self, kind: Kind, draft: EntryDraft) -> Entry:
        async with self.uow() as uow:
            if kind in SINGLETON_KINDS and await uow.entries.count(kind) > 0:
                raise SingletonKindError(f"there is already a {kind}")
            await _check_references(uow, kind, draft, exclude=None)
            entry = Entry.new(uuid4(), kind, draft, self.clock.now())
            await uow.entries.add(entry)
            await uow.commit()
        return entry


@dataclass(frozen=True, slots=True)
class UpdateEntry:
    """Optimistic concurrency: the client sends the version it edited."""

    uow: UnitOfWorkFactory
    clock: Clock

    async def __call__(self, entry_id: UUID, expected_version: int, draft: EntryDraft) -> Entry:
        async with self.uow() as uow:
            entry = await _load(uow, entry_id, expected_version)
            await _check_references(uow, entry.kind, draft, exclude=entry.id)
            entry = entry.edited(draft, self.clock.now())
            await uow.entries.save(entry)
            if entry.status is Status.PUBLISHED:
                uow.record(entry_published(entry))  # live content changed: reindex
            await uow.commit()
        return entry


@dataclass(frozen=True, slots=True)
class PublishEntry:
    uow: UnitOfWorkFactory
    clock: Clock

    async def __call__(self, entry_id: UUID, expected_version: int) -> Entry:
        async with self.uow() as uow:
            entry = (await _load(uow, entry_id, expected_version)).published(self.clock.now())
            await uow.entries.save(entry)
            uow.record(entry_published(entry))
            await uow.commit()
        return entry


@dataclass(frozen=True, slots=True)
class UnpublishEntry:
    uow: UnitOfWorkFactory
    clock: Clock

    async def __call__(self, entry_id: UUID, expected_version: int) -> Entry:
        async with self.uow() as uow:
            entry = await _load(uow, entry_id, expected_version)
            if entry.status is Status.DRAFT:
                return entry
            entry = entry.unpublished(self.clock.now())
            await uow.entries.save(entry)
            uow.record(entry_unpublished(entry))
            await uow.commit()
        return entry


@dataclass(frozen=True, slots=True)
class DeleteEntry:
    uow: UnitOfWorkFactory

    async def __call__(self, entry_id: UUID) -> None:
        async with self.uow() as uow:
            entry = await _load(uow, entry_id, expected_version=None)
            await uow.entries.delete(entry.id)
            if entry.status is Status.PUBLISHED:
                uow.record(entry_deleted(entry.id))
            await uow.commit()


@dataclass(frozen=True, slots=True)
class GetEntry:
    uow: UnitOfWorkFactory

    async def __call__(self, entry_id: UUID) -> Entry:
        async with self.uow() as uow:
            entry = await uow.entries.get(entry_id)
        if entry is None:
            raise EntryNotFoundError(entry_id)
        return entry


@dataclass(frozen=True, slots=True)
class ListEntries:
    uow: UnitOfWorkFactory

    async def __call__(self, kind: Kind | None = None, status: Status | None = None) -> list[Entry]:
        async with self.uow() as uow:
            return await uow.entries.list(kind, status)


@dataclass(frozen=True, slots=True)
class ContentUseCases:
    create: CreateEntry
    update: UpdateEntry
    publish: PublishEntry
    unpublish: UnpublishEntry
    delete: DeleteEntry
    get: GetEntry
    list: ListEntries
