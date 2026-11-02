from collections.abc import Collection
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from portfolio.contexts.files.domain.model import FileInUseError, StoredFile
from portfolio.platform.db import Base


class FileRow(Base):
    __tablename__ = "files_objects"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    filename: Mapped[str] = mapped_column(String(120))
    content_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _to_file(row: FileRow) -> StoredFile:
    return StoredFile(
        id=row.id,
        key=row.key,
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        sha256=row.sha256,
        created_at=row.created_at,
    )


class SqlFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, file_id: UUID) -> StoredFile | None:
        row = await self._session.get(FileRow, file_id)
        return _to_file(row) if row is not None else None

    async def get_many(self, ids: Collection[UUID]) -> list[StoredFile]:
        rows = await self._session.scalars(select(FileRow).where(FileRow.id.in_(list(ids))))
        return [_to_file(row) for row in rows]

    async def list(self) -> list[StoredFile]:
        rows = await self._session.scalars(select(FileRow).order_by(FileRow.created_at.desc()))
        return [_to_file(row) for row in rows]

    async def add(self, stored: StoredFile) -> None:
        self._session.add(
            FileRow(
                id=stored.id,
                key=stored.key,
                filename=stored.filename,
                content_type=stored.content_type,
                size=stored.size,
                sha256=stored.sha256,
                created_at=stored.created_at,
            )
        )

    async def delete(self, file_id: UUID) -> None:
        await self._session.execute(delete(FileRow).where(FileRow.id == file_id))


class SqlFilesUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @property
    def files(self) -> SqlFileRepository:
        return self._files

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._files = SqlFileRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._session.close()

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            if "fk_content_attachments_file_id_files_objects" in str(error.orig):
                raise FileInUseError("an entry still offers this file for download") from error
            raise
