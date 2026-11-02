"""In-memory adapters for every port outside identity (identity has its own fakes).

Each unit of work copies the store on enter and writes it back only on commit, so
"forgot to commit" bugs show up in unit tests exactly as they would in Postgres.
"""

import copy
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from portfolio.bridges import FilesAttachmentCatalog
from portfolio.contexts.contacts.application.use_cases import (
    ContactsUseCases,
    DeleteContact,
    GetContact,
    ListContacts,
    PurgeExpiredContacts,
    SetContactStatus,
    SubmitContact,
)
from portfolio.contexts.contacts.domain.model import (
    ContactRequest,
    ContactStatus,
    DuplicateSubmissionError,
    OutgoingEmail,
)
from portfolio.contexts.content.application.catalog import PublicCatalog
from portfolio.contexts.content.application.use_cases import (
    ContentUseCases,
    CreateEntry,
    DeleteEntry,
    GetEntry,
    ListEntries,
    PublishEntry,
    UnpublishEntry,
    UpdateEntry,
)
from portfolio.contexts.content.domain.entry import Entry
from portfolio.contexts.content.domain.errors import UnknownFileError
from portfolio.contexts.content.domain.events import ContentEvent
from portfolio.contexts.content.domain.kinds import Kind, Status
from portfolio.contexts.content.domain.richtext import RenderOptions
from portfolio.contexts.files.application.use_cases import (
    DeleteFile,
    DescribeFiles,
    FilesUseCases,
    ListFiles,
    UploadFile,
)
from portfolio.contexts.files.domain.model import FileInUseError, StoredFile
from tests.unit.identity.fakes import FixedClock


class _Transaction:
    """Base for the fakes: snapshot on enter, publish on commit."""

    def __init__(self, store: Any) -> None:
        self._store = store

    async def __aenter__(self) -> Self:
        self._staged = copy.copy(self._store.data)
        self._pending: list[tuple[str, dict[str, Any]]] = []
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self._before_commit()
        self._store.data = copy.copy(self._staged)
        self._store.events.extend(self._pending)
        self._pending = []

    def _before_commit(self) -> None:
        return None


# --- content ------------------------------------------------------------------


class LiveFileIds:
    """The ids currently in a FilesStore: content's foreign key, as Postgres sees it."""

    def __init__(self, store: "FilesStore") -> None:
        self._store = store

    def __contains__(self, file_id: object) -> bool:
        return file_id in self._store.data


@dataclass
class ContentStore:
    data: dict[UUID, Entry] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    files: "set[UUID] | LiveFileIds" = field(default_factory=set)


class InMemoryEntries:
    def __init__(self, staged: dict[UUID, Entry]) -> None:
        self._staged = staged

    async def get(self, entry_id: UUID, *, for_update: bool = False) -> Entry | None:
        return self._staged.get(entry_id)

    async def list(self, kind: Kind | None, status: Status | None) -> list[Entry]:
        return [
            e
            for e in sorted(self._staged.values(), key=lambda e: (e.kind, e.content.position))
            if (kind is None or e.kind is kind) and (status is None or e.status is status)
        ]

    async def get_by_slug(self, kind: Kind, slug: str) -> Entry | None:
        return next((e for e in self._staged.values() if e.kind is kind and e.slug == slug), None)

    async def slug_taken(self, kind: Kind, slug: str, exclude: UUID | None) -> bool:
        return any(
            e.kind is kind and e.slug == slug and e.id != exclude for e in self._staged.values()
        )

    async def count(self, kind: Kind) -> int:
        return sum(e.kind is kind for e in self._staged.values())

    async def existing_skills(self, ids: Collection[UUID]) -> set[UUID]:
        return {i for i in ids if i in self._staged and self._staged[i].kind is Kind.SKILL}

    async def add(self, entry: Entry) -> None:
        self._staged[entry.id] = entry

    async def save(self, entry: Entry) -> None:
        self._staged[entry.id] = entry

    async def delete(self, entry_id: UUID) -> None:
        self._staged.pop(entry_id, None)


class InMemoryContentUoW(_Transaction):
    _store: ContentStore

    @property
    def entries(self) -> InMemoryEntries:
        return InMemoryEntries(self._staged)

    def record(self, event: ContentEvent) -> None:
        self._pending.append((event.topic, event.payload))

    def _before_commit(self) -> None:
        # Mirrors the foreign key from attachments to files.
        for entry in self._staged.values():
            for attachment in entry.content.attachments:
                if attachment.file_id not in self._store.files:
                    raise UnknownFileError(str(attachment.file_id))


def content_catalog(store: ContentStore, files: FilesUseCases) -> PublicCatalog:
    return PublicCatalog(
        uow=lambda: InMemoryContentUoW(store),
        files=FilesAttachmentCatalog(files.describe),
        render=RenderOptions(image_base_url="https://files.test"),
    )


def content_use_cases(store: ContentStore, clock: FixedClock) -> ContentUseCases:
    def uow() -> InMemoryContentUoW:
        return InMemoryContentUoW(store)

    return ContentUseCases(
        create=CreateEntry(uow, clock),
        update=UpdateEntry(uow, clock),
        publish=PublishEntry(uow, clock),
        unpublish=UnpublishEntry(uow, clock),
        delete=DeleteEntry(uow),
        get=GetEntry(uow),
        list=ListEntries(uow),
    )


# --- files --------------------------------------------------------------------


@dataclass
class FilesStore:
    data: dict[UUID, StoredFile] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    in_use: set[UUID] = field(default_factory=set)
    fail_commit: bool = False


class InMemoryFiles:
    def __init__(self, staged: dict[UUID, StoredFile]) -> None:
        self._staged = staged

    async def get(self, file_id: UUID) -> StoredFile | None:
        return self._staged.get(file_id)

    async def get_many(self, ids: Collection[UUID]) -> list[StoredFile]:
        return [self._staged[i] for i in ids if i in self._staged]

    async def list(self) -> list[StoredFile]:
        return sorted(self._staged.values(), key=lambda f: f.created_at, reverse=True)

    async def add(self, stored: StoredFile) -> None:
        self._staged[stored.id] = stored

    async def delete(self, file_id: UUID) -> None:
        self._staged.pop(file_id, None)


class InMemoryFilesUoW(_Transaction):
    _store: FilesStore

    @property
    def files(self) -> InMemoryFiles:
        return InMemoryFiles(self._staged)

    def _before_commit(self) -> None:
        if self._store.fail_commit:
            raise RuntimeError("database down")
        if any(file_id not in self._staged for file_id in self._store.in_use):
            raise FileInUseError("attached")


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, str]] = {}
        self.fail_delete = False

    async def put(self, key: str, data: bytes, content_type: str, filename: str) -> None:
        self.objects[key] = (data, content_type, filename)

    async def delete(self, key: str) -> None:
        if self.fail_delete:
            raise ConnectionError("storage down")
        self.objects.pop(key, None)

    def public_url(self, key: str) -> str:
        return f"https://files.test/{key}"


def files_use_cases(store: FilesStore, storage: FakeStorage, clock: FixedClock) -> FilesUseCases:
    def uow() -> InMemoryFilesUoW:
        return InMemoryFilesUoW(store)

    return FilesUseCases(
        upload=UploadFile(uow, storage, clock),
        list=ListFiles(uow, storage),
        describe=DescribeFiles(uow, storage),
        delete=DeleteFile(uow, storage),
    )


# --- contacts -----------------------------------------------------------------


@dataclass
class ContactsStore:
    data: dict[UUID, ContactRequest] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # Simulates a concurrent retry that committed first with this key.
    race_with: ContactRequest | None = None


class InMemoryContacts:
    def __init__(self, staged: dict[UUID, ContactRequest]) -> None:
        self._staged = staged

    async def get(self, contact_id: UUID) -> ContactRequest | None:
        return self._staged.get(contact_id)

    async def get_by_idempotency_key(self, key: str) -> ContactRequest | None:
        return next((c for c in self._staged.values() if c.idempotency_key == key), None)

    async def list(self, status: ContactStatus | None) -> list[ContactRequest]:
        return [
            c
            for c in sorted(self._staged.values(), key=lambda c: c.created_at, reverse=True)
            if status is None or c.status is status
        ]

    async def add(self, request: ContactRequest) -> None:
        self._staged[request.id] = request

    async def save(self, request: ContactRequest) -> None:
        self._staged[request.id] = request

    async def delete(self, contact_id: UUID) -> None:
        self._staged.pop(contact_id, None)

    async def thanked_since(self, email: str, since: datetime) -> bool:
        return any(
            (reply := c.reply_email()) is not None
            and reply.value == email
            and c.thanked_at is not None
            and c.thanked_at >= since
            for c in self._staged.values()
        )

    async def delete_created_before(self, cutoff: datetime) -> int:
        old = [i for i, c in self._staged.items() if c.created_at < cutoff]
        for contact_id in old:
            del self._staged[contact_id]
        return len(old)


class InMemoryContactsUoW(_Transaction):
    _store: ContactsStore

    @property
    def contacts(self) -> InMemoryContacts:
        return InMemoryContacts(self._staged)

    def record(self, topic: str, payload: dict[str, Any]) -> None:
        self._pending.append((topic, payload))

    def _before_commit(self) -> None:
        race = self._store.race_with
        if race is not None:
            self._store.data[race.id] = race
            self._store.race_with = None
            raise DuplicateSubmissionError
        keys = Counter(c.idempotency_key for c in self._staged.values() if c.idempotency_key)
        if any(count > 1 for count in keys.values()):
            raise DuplicateSubmissionError


class FakeLimiter:
    """Allows `limit` hits per (bucket, key); windows are ignored."""

    def __init__(self) -> None:
        self.hits: Counter[tuple[str, str]] = Counter()

    async def hit(self, bucket: str, key: str, limit: int, window: timedelta) -> bool:
        self.hits[(bucket, key)] += 1
        return self.hits[(bucket, key)] <= limit


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []
        self.fail = False

    async def send(self, email: OutgoingEmail) -> None:
        if self.fail:
            raise ConnectionError("resend down")
        self.sent.append(email)


def contacts_use_cases(
    store: ContactsStore, limiter: FakeLimiter, clock: FixedClock
) -> ContactsUseCases:
    def uow() -> InMemoryContactsUoW:
        return InMemoryContactsUoW(store)

    return ContactsUseCases(
        submit=SubmitContact(uow, limiter, clock),
        list=ListContacts(uow),
        get=GetContact(uow),
        set_status=SetContactStatus(uow),
        delete=DeleteContact(uow),
        purge_expired=PurgeExpiredContacts(uow, clock),
    )


def contacts_uow_factory(store: ContactsStore) -> Any:
    return lambda: InMemoryContactsUoW(store)
