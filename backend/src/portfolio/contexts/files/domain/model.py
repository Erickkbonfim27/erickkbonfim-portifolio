"""Uploaded files. The type is decided by the file's bytes, never by its name or the
browser's Content-Type, so a renamed executable cannot pass as a PDF."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class FilesError(Exception):
    pass


class UnsupportedFileError(FilesError):
    pass


class FileTooLargeError(FilesError):
    pass


class MissingFileError(FilesError):
    def __init__(self, file_id: UUID) -> None:
        super().__init__(f"file {file_id} not found")


class FileInUseError(FilesError):
    """An entry still offers this file for download."""


MAX_SIZE = 25 * 1024 * 1024
MAX_FILENAME = 120


@dataclass(frozen=True, slots=True)
class MediaType:
    extension: str
    mime: str


_PDF = MediaType("pdf", "application/pdf")
_PNG = MediaType("png", "image/png")
_JPEG = MediaType("jpg", "image/jpeg")
_GIF = MediaType("gif", "image/gif")
_WEBP = MediaType("webp", "image/webp")
_ZIP = MediaType("zip", "application/zip")

# SVG and HTML are left out on purpose: they can carry scripts.
SUPPORTED = (_PDF, _PNG, _JPEG, _GIF, _WEBP, _ZIP)


def detect_type(head: bytes) -> MediaType:
    """Identify the file from its first bytes (magic numbers)."""
    if head.startswith(b"%PDF-"):
        return _PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return _PNG
    if head.startswith(b"\xff\xd8\xff"):
        return _JPEG
    if head.startswith((b"GIF87a", b"GIF89a")):
        return _GIF
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return _WEBP
    if head.startswith(b"PK\x03\x04"):
        return _ZIP
    raise UnsupportedFileError("allowed: PDF, PNG, JPEG, GIF, WebP, ZIP")


def clean_filename(raw: str, media: MediaType) -> str:
    """The name shown in the download dialog: no path, no control characters, right extension."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w\s.()\-]", "", name).strip(" .")
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = re.sub(r"\s+", " ", stem)[: MAX_FILENAME - len(media.extension) - 1].strip() or "file"
    return f"{stem}.{media.extension}"


@dataclass(frozen=True, slots=True)
class StoredFile:
    id: UUID
    key: str
    filename: str
    content_type: str
    size: int
    sha256: str
    created_at: datetime
