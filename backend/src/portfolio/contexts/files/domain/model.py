"""Uploaded files. The type is decided by the file's bytes, never by its name or the
browser's Content-Type, so a renamed executable cannot pass as a PDF.

Photos (PNG, JPEG, WebP, HEIC) are re-encoded to WebP before they are stored: a
phone photo carries its GPS position in EXIF, and re-encoding drops all metadata.
"""

import json
import re
import unicodedata
from collections.abc import Callable
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
_HEIC = MediaType("heic", "image/heic")
GEOJSON = MediaType("geojson", "application/geo+json")
WEBP = _WEBP

# SVG and HTML are left out on purpose: they can carry scripts.
SUPPORTED = (_PDF, _PNG, _JPEG, _GIF, _WEBP, _ZIP, _HEIC, GEOJSON)
# Re-encoded to WebP on upload. GIF is kept as is: it may be animated.
PHOTOS = frozenset({_PNG, _JPEG, _WEBP, _HEIC})
_HEIF_BRANDS = frozenset({b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"})
_GEOJSON_TYPES = frozenset({"FeatureCollection", "Feature"})
HEAD_SIZE = 16


_SIGNATURES: tuple[tuple[Callable[[bytes], bool], MediaType], ...] = (
    (lambda h: h[4:8] == b"ftyp" and h[8:12] in _HEIF_BRANDS, _HEIC),
    (lambda h: h.startswith(b"%PDF-"), _PDF),
    (lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"), _PNG),
    (lambda h: h.startswith(b"\xff\xd8\xff"), _JPEG),
    (lambda h: h.startswith((b"GIF87a", b"GIF89a")), _GIF),
    (lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP", _WEBP),
    (lambda h: h.startswith(b"PK\x03\x04"), _ZIP),
    # Confirmed by `check_geojson`, which reads the whole file.
    (lambda h: h.lstrip().startswith(b"{"), GEOJSON),
)


def detect_type(head: bytes) -> MediaType:
    """Identify the file from its first bytes (magic numbers)."""
    for matches, media in _SIGNATURES:
        if matches(head):
            return media
    raise UnsupportedFileError("allowed: PDF, PNG, JPEG, GIF, WebP, HEIC, ZIP, GeoJSON")


def check_geojson(data: bytes) -> None:
    """Map layers are data, never markup: the whole file must parse as GeoJSON."""
    try:
        document = json.loads(data)
    except (UnicodeDecodeError, ValueError):
        raise UnsupportedFileError("the file is not valid JSON") from None
    if not isinstance(document, dict) or document.get("type") not in _GEOJSON_TYPES:
        raise UnsupportedFileError("JSON files must be a GeoJSON Feature or FeatureCollection")


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
