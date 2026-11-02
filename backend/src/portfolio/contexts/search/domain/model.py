"""Search documents, chunks and queries. No I/O."""

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

# Fixed namespace: the same entry, language and position always get the same point
# id, so re-indexing overwrites instead of duplicating.
_CHUNK_NAMESPACE = UUID("6f1d3c56-6b7e-4f0a-9d0e-2a8b8f7f5e11")

MAX_CHUNK_CHARS = 1200
MAX_QUERY_CHARS = 300
MAX_RESULTS = 20
LANGS = ("en", "pt")


class SearchError(Exception):
    pass


class InvalidQueryError(SearchError):
    pass


@dataclass(frozen=True, slots=True)
class Section:
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One published entry in one language, as plain text."""

    entry_id: UUID
    kind: str
    slug: str
    lang: str
    title: str
    summary: str
    facts: tuple[str, ...]
    tags: tuple[str, ...]
    sections: tuple[Section, ...]


@dataclass(frozen=True, slots=True)
class Chunk:
    id: UUID
    entry_id: UUID
    kind: str
    slug: str
    lang: str
    position: int
    title: str
    heading: str
    text: str

    @property
    def indexed_text(self) -> str:
        """What the encoders see: the title and heading give each chunk its context."""
        parts = [self.title, self.heading, self.text]
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class SparseVector:
    indices: tuple[int, ...]
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    lang: str
    limit: int
    kinds: tuple[str, ...] = ()

    @classmethod
    def build(
        cls, text: str, lang: str = "en", limit: int = 5, kinds: tuple[str, ...] = ()
    ) -> "SearchQuery":
        text = " ".join(text.split())
        if not text:
            raise InvalidQueryError("the query is empty")
        if len(text) > MAX_QUERY_CHARS:
            raise InvalidQueryError(f"the query is limited to {MAX_QUERY_CHARS} characters")
        if lang not in LANGS:
            raise InvalidQueryError(f"lang must be one of {list(LANGS)}")
        if not 1 <= limit <= MAX_RESULTS:
            raise InvalidQueryError(f"limit must be between 1 and {MAX_RESULTS}")
        return cls(text, lang, limit, kinds)


@dataclass(frozen=True, slots=True)
class SearchHit:
    entry_id: UUID
    kind: str
    slug: str
    title: str
    heading: str
    text: str
    score: float


def chunk_id(entry_id: UUID, lang: str, position: int) -> UUID:
    return uuid.uuid5(_CHUNK_NAMESPACE, f"{entry_id}:{lang}:{position}")


def _split(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack paragraphs into pieces of at most `limit` characters; split long paragraphs
    at sentence ends, and as a last resort at the limit itself."""
    units: list[str] = []
    for paragraph in (p.strip() for p in text.split("\n")):
        if not paragraph:
            continue
        sentences = (
            [paragraph] if len(paragraph) <= limit else re.split(r"(?<=[.!?])\s+", paragraph)
        )
        for sentence in sentences:
            units.extend(sentence[i : i + limit] for i in range(0, len(sentence), limit))
    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n{unit}" if current else unit
        if len(candidate) <= limit:
            current = candidate
        else:
            pieces.append(current)
            current = unit
    if current:
        pieces.append(current)
    return pieces


def chunk_document(document: SourceDocument) -> list[Chunk]:
    """An overview chunk (summary, facts such as the organization, tags), then the body
    split at its headings."""
    texts: list[tuple[str, str]] = []
    parts = (document.summary, " · ".join(document.facts), ", ".join(document.tags))
    overview = "\n".join(part for part in parts if part)
    texts.append(("", overview))
    for section in document.sections:
        texts.extend((section.heading, piece) for piece in _split(section.text))
    return [
        Chunk(
            id=chunk_id(document.entry_id, document.lang, position),
            entry_id=document.entry_id,
            kind=document.kind,
            slug=document.slug,
            lang=document.lang,
            position=position,
            title=document.title,
            heading=heading,
            text=text,
        )
        for position, (heading, text) in enumerate(texts)
    ]
