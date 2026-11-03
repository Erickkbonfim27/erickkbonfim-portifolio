from collections.abc import Collection
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from portfolio.contexts.files.domain.model import StoredFile


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str, filename: str) -> None:
        """Store the object so browsers download it as `filename`."""
        ...

    async def delete(self, key: str) -> None: ...

    def public_url(self, key: str) -> str: ...


class FileRepository(Protocol):
    async def get(self, file_id: UUID) -> StoredFile | None: ...
    async def get_many(self, ids: Collection[UUID]) -> list[StoredFile]: ...
    async def find_by_sha256(self, sha256: str) -> StoredFile | None: ...
    async def list(self) -> list[StoredFile]: ...
    async def add(self, stored: StoredFile) -> None: ...
    async def delete(self, file_id: UUID) -> None: ...


class FilesUnitOfWork(Protocol):
    @property
    def files(self) -> FileRepository: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None:
        """Raises FileInUseError when a deleted file is still attached to an entry."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class ImageEncoder(Protocol):
    def to_webp(self, data: bytes) -> bytes:
        """The photo upright, resized to fit the site, as WebP without any metadata.

        Raises UnsupportedFileError when the bytes are not a readable image.
        """
        ...
