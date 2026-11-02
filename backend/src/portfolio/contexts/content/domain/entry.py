"""A content entry: one experience, project, study, skill… in both languages."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from portfolio.contexts.content.domain import richtext
from portfolio.contexts.content.domain.details import parse_details
from portfolio.contexts.content.domain.errors import IncompleteEntryError, InvalidEntryError
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG = 80
MAX_TITLE = 200
MAX_SUMMARY = 600
MAX_TAGS = 20
MAX_TAG = 40
MAX_SKILLS = 60
MAX_ATTACHMENTS = 20
MAX_LABEL = 120
MAX_POSITION = 1_000_000

# Kinds whose title alone is a complete entry (a skill is just its name).
TITLE_ONLY_KINDS = frozenset({Kind.SKILL})


@dataclass(frozen=True, slots=True)
class Translation:
    title: str
    summary: str
    body: Mapping[str, Any]

    @classmethod
    def create(cls, title: str, summary: str = "", body: object = None) -> "Translation":
        title, summary = title.strip(), summary.strip()
        if len(title) > MAX_TITLE:
            raise InvalidEntryError(f"title must be at most {MAX_TITLE} characters")
        if len(summary) > MAX_SUMMARY:
            raise InvalidEntryError(f"summary must be at most {MAX_SUMMARY} characters")
        doc = richtext.validate(body if body is not None else richtext.EMPTY_DOC)
        return cls(title, summary, doc)

    def is_complete(self, kind: Kind) -> bool:
        if not self.title:
            return False
        return kind in TITLE_ONLY_KINDS or bool(self.summary or richtext.plain_text(self.body))


@dataclass(frozen=True, slots=True)
class Attachment:
    file_id: UUID
    label: str


@dataclass(frozen=True, slots=True)
class EntryDraft:
    """Everything the admin edits, already validated. Built with `EntryDraft.build`."""

    slug: str
    translations: Mapping[Lang, Translation]
    details: Mapping[str, Any]
    tags: tuple[str, ...]
    skills: tuple[UUID, ...]
    attachments: tuple[Attachment, ...]
    position: int

    @classmethod
    def build(
        cls,
        kind: Kind,
        *,
        slug: str,
        translations: Mapping[Lang, Translation],
        details: Mapping[str, Any],
        tags: Sequence[str] = (),
        skills: Sequence[UUID] = (),
        attachments: Sequence[Attachment] = (),
        position: int = 0,
    ) -> "EntryDraft":
        if len(slug) > MAX_SLUG or not _SLUG.match(slug):
            raise InvalidEntryError("slug must be lowercase words separated by hyphens")
        if not translations:
            raise InvalidEntryError("at least one language is required")
        normalized_tags = tuple(dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip()))
        if len(normalized_tags) > MAX_TAGS or any(len(t) > MAX_TAG for t in normalized_tags):
            raise InvalidEntryError(f"up to {MAX_TAGS} tags of {MAX_TAG} characters")
        unique_skills = tuple(dict.fromkeys(skills))
        if kind is Kind.SKILL and unique_skills:
            raise InvalidEntryError("a skill cannot list skills")
        if len(unique_skills) > MAX_SKILLS:
            raise InvalidEntryError(f"up to {MAX_SKILLS} skills")
        if len(attachments) > MAX_ATTACHMENTS:
            raise InvalidEntryError(f"up to {MAX_ATTACHMENTS} attachments")
        if len({a.file_id for a in attachments}) != len(attachments):
            raise InvalidEntryError("the same file is attached twice")
        for attachment in attachments:
            if not attachment.label.strip() or len(attachment.label) > MAX_LABEL:
                raise InvalidEntryError(f"attachment labels need 1 to {MAX_LABEL} characters")
        if not -MAX_POSITION <= position <= MAX_POSITION:
            raise InvalidEntryError("position out of range")
        return cls(
            slug=slug,
            translations=MappingProxyType(dict(translations)),
            details=MappingProxyType(parse_details(kind, details)),
            tags=normalized_tags,
            skills=unique_skills,
            attachments=tuple(replace(a, label=a.label.strip()) for a in attachments),
            position=position,
        )


@dataclass(frozen=True, slots=True)
class Entry:
    id: UUID
    kind: Kind
    status: Status
    version: int
    content: EntryDraft
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None

    @property
    def slug(self) -> str:
        return self.content.slug

    @classmethod
    def new(cls, entry_id: UUID, kind: Kind, content: EntryDraft, now: datetime) -> "Entry":
        return cls(
            id=entry_id,
            kind=kind,
            status=Status.DRAFT,
            version=1,
            content=_stamp_availability(kind, None, content, now),
            created_at=now,
            updated_at=now,
        )

    def edited(self, content: EntryDraft, now: datetime) -> "Entry":
        return replace(
            self,
            content=_stamp_availability(self.kind, self.content, content, now),
            version=self.version + 1,
            updated_at=now,
        )

    def published(self, now: datetime) -> "Entry":
        missing = [
            lang.value
            for lang in Lang
            if lang not in self.content.translations
            or not self.content.translations[lang].is_complete(self.kind)
        ]
        if missing:
            raise IncompleteEntryError(f"fill in every language before publishing: {missing}")
        return replace(
            self,
            status=Status.PUBLISHED,
            version=self.version + 1,
            updated_at=now,
            published_at=self.published_at or now,
        )

    def unpublished(self, now: datetime) -> "Entry":
        return replace(self, status=Status.DRAFT, version=self.version + 1, updated_at=now)


def _stamp_availability(
    kind: Kind, before: EntryDraft | None, after: EntryDraft, now: datetime
) -> EntryDraft:
    """The profile records when availability last changed, so agents can trust it."""
    if kind is not Kind.PROFILE:
        return after
    previous = before.details if before is not None else {}
    details = dict(after.details)
    stamp = previous.get("availability_updated_at")
    if previous.get("availability") != details.get("availability"):
        stamp = None
    details["availability_updated_at"] = stamp or now.date().isoformat()
    return replace(after, details=MappingProxyType(details))
