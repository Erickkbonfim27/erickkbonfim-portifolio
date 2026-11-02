"""The public, read-only side of content: what visitors, agents and the site see.

Only published entries, in one language, with rich text already rendered to safe
HTML and attachments resolved to download URLs.
"""

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from portfolio.contexts.content.application.ports import ContentUnitOfWork
from portfolio.contexts.content.domain import richtext
from portfolio.contexts.content.domain.entry import Entry, Translation
from portfolio.contexts.content.domain.errors import NoSuchEntryError
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status


@dataclass(frozen=True, slots=True)
class FileView:
    filename: str
    url: str
    content_type: str
    size: int


class AttachmentCatalog(Protocol):
    """Implemented outside this context: files belong to the files context."""

    async def describe(self, ids: Collection[UUID]) -> Mapping[UUID, FileView]: ...


@dataclass(frozen=True, slots=True)
class AttachmentView:
    label: str
    file: FileView


@dataclass(frozen=True, slots=True)
class SkillRef:
    slug: str
    title: str


@dataclass(frozen=True, slots=True)
class PublicEntry:
    kind: Kind
    slug: str
    title: str
    summary: str
    tags: tuple[str, ...]
    details: Mapping[str, Any]
    body_html: str
    body_text: str
    skills: tuple[SkillRef, ...]
    attachments: tuple[AttachmentView, ...]
    published_at: datetime
    updated_at: datetime


AvailabilityStatus = Literal["open", "not_looking", "unknown"]


@dataclass(frozen=True, slots=True)
class Availability:
    status: AvailabilityStatus
    updated_at: str | None

    @property
    def open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True, slots=True)
class PublicProfile:
    name: str
    headline: str
    summary: str
    bio_html: str
    location: str | None
    email: str | None
    links: tuple[Mapping[str, str], ...]
    availability: Availability
    attachments: tuple[AttachmentView, ...]


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: Kind
    slug: str
    title: str


@dataclass(frozen=True, slots=True)
class PublicSkill:
    slug: str
    title: str
    category: str
    evidence: tuple[Evidence, ...]


_DATE_FIELDS = ("start", "issued", "published")


def _ordered(entries: Sequence[Entry]) -> list[Entry]:
    """Admin position first; within the same position, most recent first."""

    def date(entry: Entry) -> str:
        details = entry.content.details
        return next((str(details[f]) for f in _DATE_FIELDS if f in details), "")

    newest_first = sorted(entries, key=date, reverse=True)
    return sorted(newest_first, key=lambda e: e.content.position)


def _text(entry: Entry, lang: Lang) -> Translation:
    # Publishing requires every language; English is a guard, not a feature.
    translations = entry.content.translations
    return translations.get(lang) or translations[Lang.EN]


UnitOfWorkFactory = Callable[[], ContentUnitOfWork]


@dataclass(frozen=True, slots=True)
class PublicCatalog:
    uow: UnitOfWorkFactory
    files: AttachmentCatalog
    render: richtext.RenderOptions

    async def _published(self, kind: Kind | None) -> list[Entry]:
        async with self.uow() as uow:
            return await uow.entries.list(kind, Status.PUBLISHED)

    async def _attachments(self, entries: Sequence[Entry]) -> Mapping[UUID, FileView]:
        ids = {a.file_id for e in entries for a in e.content.attachments}
        return await self.files.describe(ids)

    def _view(
        self,
        entry: Entry,
        lang: Lang,
        skills: Mapping[UUID, SkillRef],
        files: Mapping[UUID, FileView],
    ) -> PublicEntry:
        text = _text(entry, lang)
        return PublicEntry(
            kind=entry.kind,
            slug=entry.slug,
            title=text.title,
            summary=text.summary,
            tags=entry.content.tags,
            details=entry.content.details,
            body_html=richtext.render_html(text.body, self.render),
            body_text=richtext.plain_text(text.body),
            # Draft skills are left out: the public never sees a draft, not even by name.
            skills=tuple(skills[s] for s in entry.content.skills if s in skills),
            attachments=tuple(
                AttachmentView(a.label, files[a.file_id])
                for a in entry.content.attachments
                if a.file_id in files
            ),
            published_at=entry.published_at or entry.updated_at,
            updated_at=entry.updated_at,
        )

    async def _skill_refs(self, lang: Lang) -> dict[UUID, SkillRef]:
        return {
            s.id: SkillRef(s.slug, _text(s, lang).title) for s in await self._published(Kind.SKILL)
        }

    async def entries(
        self, kind: Kind, lang: Lang, collection: str | None = None
    ) -> list[PublicEntry]:
        entries = [
            e
            for e in _ordered(await self._published(kind))
            if collection is None or e.content.details.get("collection") == collection
        ]
        skills = await self._skill_refs(lang)
        files = await self._attachments(entries)
        return [self._view(e, lang, skills, files) for e in entries]

    async def entry(self, kind: Kind, slug: str, lang: Lang) -> PublicEntry:
        async with self.uow() as uow:
            entry = await uow.entries.get_by_slug(kind, slug)
        if entry is None or entry.status is not Status.PUBLISHED:
            raise NoSuchEntryError(kind.value, slug)
        skills = await self._skill_refs(lang)
        return self._view(entry, lang, skills, await self._attachments([entry]))

    async def profile(self, lang: Lang) -> PublicProfile | None:
        published = await self._published(Kind.PROFILE)
        if not published:
            return None
        entry = published[0]
        view = self._view(entry, lang, {}, await self._attachments([entry]))
        details = entry.content.details
        return PublicProfile(
            name=str(details["name"]),
            headline=view.title,
            summary=view.summary,
            bio_html=view.body_html,
            location=details.get("location"),
            email=details.get("email"),
            links=tuple(details.get("links", ())),
            availability=_availability(entry),
            attachments=view.attachments,
        )

    async def availability(self) -> Availability:
        published = await self._published(Kind.PROFILE)
        return _availability(published[0]) if published else Availability("unknown", None)

    async def skills(self, lang: Lang) -> list[PublicSkill]:
        everything = await self._published(None)
        skills = _ordered([e for e in everything if e.kind is Kind.SKILL])
        used_in: dict[UUID, list[Evidence]] = {s.id: [] for s in skills}
        for entry in _ordered([e for e in everything if e.kind is not Kind.SKILL]):
            for skill_id in entry.content.skills:
                if skill_id in used_in:
                    used_in[skill_id].append(
                        Evidence(entry.kind, entry.slug, _text(entry, lang).title)
                    )
        return [
            PublicSkill(
                slug=s.slug,
                title=_text(s, lang).title,
                category=str(s.content.details["category"]),
                evidence=tuple(used_in[s.id]),
            )
            for s in skills
        ]


def _availability(profile: Entry) -> Availability:
    details = profile.content.details
    status: AvailabilityStatus = "open" if details.get("availability") == "open" else "not_looking"
    return Availability(status, details.get("availability_updated_at"))


@dataclass(frozen=True, slots=True)
class IndexText:
    """Plain text of one published entry in one language, for the search index."""

    entry_id: UUID
    kind: Kind
    slug: str
    lang: Lang
    title: str
    summary: str
    facts: tuple[str, ...]
    tags: tuple[str, ...]
    sections: tuple[richtext.Section, ...]


# Structured fields that name things people search for ("Loopia", "PUCRS").
FACT_FIELDS = ("organization", "institution", "issuer", "author", "location")

# Skills are names, not text: they are found through the entries that use them.
NOT_INDEXED = frozenset({Kind.SKILL})


def _index_texts(entry: Entry) -> list[IndexText]:
    return [
        IndexText(
            entry_id=entry.id,
            kind=entry.kind,
            slug=entry.slug,
            lang=lang,
            title=text.title,
            summary=text.summary,
            facts=tuple(
                str(entry.content.details[f]) for f in FACT_FIELDS if f in entry.content.details
            ),
            tags=entry.content.tags,
            sections=tuple(richtext.sections(text.body)),
        )
        for lang, text in entry.content.translations.items()
    ]


@dataclass(frozen=True, slots=True)
class IndexFeed:
    uow: UnitOfWorkFactory

    async def entry(self, entry_id: UUID) -> list[IndexText]:
        """Every language of one entry; empty when it is not published (or gone)."""
        async with self.uow() as uow:
            entry = await uow.entries.get(entry_id)
        if entry is None or entry.status is not Status.PUBLISHED or entry.kind in NOT_INDEXED:
            return []
        return _index_texts(entry)

    async def everything(self) -> list[IndexText]:
        async with self.uow() as uow:
            published = await uow.entries.list(None, Status.PUBLISHED)
        return [t for e in published if e.kind not in NOT_INDEXED for t in _index_texts(e)]
