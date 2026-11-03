"""Adapters that let one context use another without importing it.

A context declares a port in its own terms (content's `AttachmentCatalog`); the
composition root plugs in an adapter built on the other context's use cases.
"""

import time
from collections.abc import Callable, Collection, Mapping
from uuid import UUID

from portfolio.contexts.assistant.application.ports import Lookup, Ranked
from portfolio.contexts.assistant.domain.evidence import Passage
from portfolio.contexts.content.application.catalog import (
    FileView,
    IndexFeed,
    IndexText,
    PublicCatalog,
    PublicEntry,
)
from portfolio.contexts.content.domain.errors import NoSuchEntryError
from portfolio.contexts.content.domain.kinds import Kind, Lang
from portfolio.contexts.files.application.use_cases import DescribeFiles
from portfolio.contexts.search.application.use_cases import Search
from portfolio.contexts.search.domain.model import (
    InvalidQueryError,
    SearchQuery,
    Section,
    SourceDocument,
)

PROFILE_TTL_SECONDS = 300.0


CARD = {
    "en": {
        "location": "Location",
        "career": "Career",
        "building": "Building now",
        "until": "to",
        "present": "now",
    },
    "pt": {
        "location": "Onde",
        "career": "Carreira",
        "building": "Construindo agora",
        "until": "até",
        "present": "hoje",
    },
}


def _job(entry: PublicEntry, words: Mapping[str, str]) -> str:
    details = entry.details
    end = details.get("end") or words["present"]
    since = f"{details['start']} {words['until']} {end}" if details.get("start") else end
    return f"{entry.title}, {details.get('organization', '')} ({since})"


def _first_sentence(text: str) -> str:
    end = min((i for i in (text.find(". "), text.find(": ")) if i > 0), default=len(text))
    return text[: end + 1].strip() if end < len(text) else text.strip()


class FilesAttachmentCatalog:
    def __init__(self, describe: DescribeFiles) -> None:
        self._describe = describe

    async def describe(self, ids: Collection[UUID]) -> Mapping[UUID, FileView]:
        return {
            file_id: FileView(
                filename=public.file.filename,
                url=public.url,
                content_type=public.file.content_type,
                size=public.file.size,
            )
            for file_id, public in (await self._describe(ids)).items()
        }


def _document(text: IndexText) -> SourceDocument:
    return SourceDocument(
        entry_id=text.entry_id,
        kind=text.kind.value,
        slug=text.slug,
        lang=text.lang.value,
        title=text.title,
        summary=text.summary,
        facts=text.facts,
        tags=text.tags,
        sections=tuple(Section(s.heading, s.text) for s in text.sections),
    )


class ContentSourceCatalog:
    """Search reads published content through this, never through content's tables."""

    def __init__(self, feed: IndexFeed) -> None:
        self._feed = feed

    async def entry(self, entry_id: UUID) -> list[SourceDocument]:
        return [_document(t) for t in await self._feed.entry(entry_id)]

    async def everything(self) -> list[SourceDocument]:
        return [_document(t) for t in await self._feed.everything()]


class SiteKnowledge:
    """The assistant's `Knowledge` port, over search and the public catalog."""

    def __init__(
        self,
        search: Search,
        catalog: PublicCatalog,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._search = search
        self._catalog = catalog
        self._clock = clock
        # Every question reads the profile; it changes a few times a year.
        self._profiles: dict[str, tuple[float, Passage | None]] = {}

    async def search(self, query: str, lang: str, limit: int) -> Lookup:
        try:
            built = SearchQuery.build(query, lang, limit)
        except InvalidQueryError:
            return Lookup([])
        found = await self._search.explain(built)
        return Lookup(
            [
                Passage(hit.kind, hit.slug, hit.title, hit.heading, hit.text, hit.score)
                for hit in found.hits
            ],
            found.steps,
            [Ranked(h.title, h.heading, h.score) for h in found.dense],
            [Ranked(h.title, h.heading, h.score) for h in found.sparse],
        )

    async def case(self, slug: str, lang: str) -> Passage | None:
        try:
            entry = await self._catalog.entry(Kind.PROJECT, slug, Lang(lang))
        except (NoSuchEntryError, ValueError):
            return None
        text = f"{entry.summary}\n\n{entry.body_text}".strip()
        return Passage("project", entry.slug, entry.title, "", text, 1.0)

    async def profile(self, lang: str) -> Passage | None:
        cached = self._profiles.get(lang)
        if cached is not None and self._clock() - cached[0] < PROFILE_TTL_SECONDS:
            return cached[1]
        passage = await self._read_profile(lang)
        self._profiles[lang] = (self._clock(), passage)
        return passage

    async def _read_profile(self, lang: str) -> Passage | None:
        if lang not in CARD:
            return None
        found = await self._catalog.profile(Lang(lang))
        if found is None:
            return None
        lines = [f"{found.name}: {found.headline}", found.summary]
        words = CARD[lang]
        if found.location:
            lines.append(f"{words['location']}: {found.location}")
        # The whole path in one place: "who is Erick" must not depend on what a search ranks.
        # One fact per line, in the visitor's language: the checks read it line by line.
        jobs = await self._catalog.entries(Kind.EXPERIENCE, Lang(lang))
        lines += [f"{words['career']}: {_job(job, words)}" for job in jobs]
        lines += [
            f"{words['building']}: {p.title}, {_first_sentence(p.summary)}"
            for p in await self._catalog.entries(Kind.PROJECT, Lang(lang))
            if p.details.get("state") in {"active", "building"}
        ]
        return Passage("profile", "profile", found.name, found.headline, "\n".join(lines), 1.0)
