import hashlib
import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass
from uuid import UUID, uuid4

from portfolio.contexts.files.application.ports import (
    Clock,
    FilesUnitOfWork,
    ImageEncoder,
    ObjectStorage,
)
from portfolio.contexts.files.domain.model import (
    GEOJSON,
    HEAD_SIZE,
    MAX_SIZE,
    PHOTOS,
    WEBP,
    FileTooLargeError,
    MissingFileError,
    StoredFile,
    UnsupportedFileError,
    check_geojson,
    clean_filename,
    detect_type,
)

log = logging.getLogger(__name__)

UnitOfWorkFactory = Callable[[], FilesUnitOfWork]


@dataclass(frozen=True, slots=True)
class PublicFile:
    file: StoredFile
    url: str


@dataclass(frozen=True, slots=True)
class UploadFile:
    uow: UnitOfWorkFactory
    storage: ObjectStorage
    clock: Clock
    images: ImageEncoder

    async def __call__(self, filename: str, data: bytes) -> PublicFile:
        if len(data) > MAX_SIZE:
            raise FileTooLargeError(f"files are limited to {MAX_SIZE // (1024 * 1024)} MB")
        if not data:
            raise UnsupportedFileError("the file is empty")
        media = detect_type(data[:HEAD_SIZE])
        if media in PHOTOS:
            data, media = self.images.to_webp(data), WEBP
        elif media is GEOJSON:
            check_geojson(data)
        sha256 = hashlib.sha256(data).hexdigest()
        async with self.uow() as uow:
            existing = await uow.files.find_by_sha256(sha256)
        if existing is not None:
            # The same bytes again (a re-run seed, a second upload): one object is enough.
            return PublicFile(existing, self.storage.public_url(existing.key))
        file_id = uuid4()
        stored = StoredFile(
            id=file_id,
            # Random key: the public bucket is not listable, so keys are not guessable.
            key=f"{file_id}.{media.extension}",
            filename=clean_filename(filename, media),
            content_type=media.mime,
            size=len(data),
            sha256=sha256,
            created_at=self.clock.now(),
        )
        # Object first, row second: a row never points at a missing object.
        await self.storage.put(stored.key, data, stored.content_type, stored.filename)
        try:
            async with self.uow() as uow:
                await uow.files.add(stored)
                await uow.commit()
        except BaseException:
            await self.storage.delete(stored.key)
            raise
        return PublicFile(stored, self.storage.public_url(stored.key))


@dataclass(frozen=True, slots=True)
class ListFiles:
    uow: UnitOfWorkFactory
    storage: ObjectStorage

    async def __call__(self) -> list[PublicFile]:
        async with self.uow() as uow:
            files = await uow.files.list()
        return [PublicFile(f, self.storage.public_url(f.key)) for f in files]


@dataclass(frozen=True, slots=True)
class DescribeFiles:
    """Public facts about some files, for pages that offer them for download."""

    uow: UnitOfWorkFactory
    storage: ObjectStorage

    async def __call__(self, ids: Collection[UUID]) -> dict[UUID, PublicFile]:
        if not ids:
            return {}
        async with self.uow() as uow:
            files = await uow.files.get_many(ids)
        return {f.id: PublicFile(f, self.storage.public_url(f.key)) for f in files}


@dataclass(frozen=True, slots=True)
class DeleteFile:
    uow: UnitOfWorkFactory
    storage: ObjectStorage

    async def __call__(self, file_id: UUID) -> None:
        async with self.uow() as uow:
            stored = await uow.files.get(file_id)
            if stored is None:
                raise MissingFileError(file_id)
            await uow.files.delete(file_id)
            await uow.commit()  # FileInUseError if an entry still attaches it
        # Row first, object second: a failure here leaves an orphan object, never a
        # row pointing at nothing.
        try:
            await self.storage.delete(stored.key)
        except Exception:
            log.warning("orphan object left in storage", extra={"key": stored.key})


@dataclass(frozen=True, slots=True)
class FilesUseCases:
    upload: UploadFile
    list: ListFiles
    describe: DescribeFiles
    delete: DeleteFile
