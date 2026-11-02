"""Admin API for files. Mounted behind the admin session in `main.py`."""

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from portfolio.contexts.files.application.use_cases import FilesUseCases, PublicFile
from portfolio.contexts.files.domain.model import (
    MAX_SIZE,
    FileInUseError,
    FileTooLargeError,
    MissingFileError,
)


def _use_cases(request: Request) -> FilesUseCases:
    return cast(FilesUseCases, request.app.state.files)


UseCases = Annotated[FilesUseCases, Depends(_use_cases)]

router = APIRouter(prefix="/admin/files", include_in_schema=False)


class FileOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size: int
    url: str
    created_at: datetime

    @classmethod
    def of(cls, public: PublicFile) -> "FileOut":
        f = public.file
        return cls(
            id=f.id,
            filename=f.filename,
            content_type=f.content_type,
            size=f.size,
            url=public.url,
            created_at=f.created_at,
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, use_cases: UseCases) -> FileOut:
    # Read one byte past the limit: enough to know it is too big without
    # holding an arbitrarily large upload in memory.
    data = await file.read(MAX_SIZE + 1)
    return FileOut.of(await use_cases.upload(file.filename or "file", data))


@router.get("")
async def list_files(use_cases: UseCases) -> list[FileOut]:
    return [FileOut.of(f) for f in await use_cases.list()]


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: UUID, use_cases: UseCases) -> None:
    await use_cases.delete(file_id)


def error_response(_: Request, error: Exception) -> JSONResponse:
    """Maps domain errors to HTTP. Registered on the app for FilesError."""
    code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if isinstance(error, MissingFileError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, FileInUseError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(error, FileTooLargeError):
        code = status.HTTP_413_CONTENT_TOO_LARGE
    return JSONResponse({"detail": str(error)}, status_code=code)
