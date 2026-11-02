"""Adapters that let one context use another without importing it.

A context declares a port in its own terms (content's `AttachmentCatalog`); the
composition root plugs in an adapter built on the other context's use cases.
"""

from collections.abc import Collection, Mapping
from uuid import UUID

from portfolio.contexts.content.application.catalog import FileView, IndexFeed, IndexText
from portfolio.contexts.files.application.use_cases import DescribeFiles
from portfolio.contexts.search.domain.model import Section, SourceDocument


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
