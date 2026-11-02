import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from portfolio.contexts.search.application.ports import (
    DenseEncoder,
    SourceCatalog,
    SparseEncoder,
    VectorIndex,
)
from portfolio.contexts.search.domain.model import (
    Chunk,
    SearchHit,
    SearchQuery,
    SourceDocument,
    SparseVector,
    chunk_document,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Writer:
    dense: DenseEncoder
    sparse: SparseEncoder
    index: VectorIndex

    async def write(self, documents: Sequence[SourceDocument]) -> list[Chunk]:
        chunks = [chunk for document in documents for chunk in chunk_document(document)]
        if not chunks:
            return []
        texts = [chunk.indexed_text for chunk in chunks]
        dense = await self.dense.documents(texts)
        by_lang: dict[str, list[int]] = defaultdict(list)
        for position, chunk in enumerate(chunks):
            by_lang[chunk.lang].append(position)
        sparse_by_position: dict[int, SparseVector] = {}
        for lang, positions in by_lang.items():
            vectors = await self.sparse.documents([texts[p] for p in positions], lang)
            sparse_by_position.update(zip(positions, vectors, strict=True))
        sparse = [sparse_by_position[p] for p in range(len(chunks))]
        await self.index.upsert(chunks, dense, sparse)
        return chunks


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """Bring one entry's chunks in line with the database.

    It always reads the current state, so a stale or repeated event is harmless:
    the index ends up matching what is published now.
    """

    catalog: SourceCatalog
    writer: _Writer

    async def __call__(self, entry_id: UUID) -> int:
        documents = await self.catalog.entry(entry_id)
        await self.writer.index.ensure(self.writer.dense.dimension)
        chunks = await self.writer.write(documents)
        # Drop chunks the entry no longer has (it got shorter, or was unpublished).
        await self.writer.index.delete_entry(entry_id, keep=[c.id for c in chunks])
        return len(chunks)


@dataclass(frozen=True, slots=True)
class Reindex:
    """`make reindex`: rebuild the whole index from the database."""

    catalog: SourceCatalog
    writer: _Writer

    async def __call__(self) -> int:
        await self.writer.index.recreate(self.writer.dense.dimension)
        return len(await self.writer.write(await self.catalog.everything()))


@dataclass(frozen=True, slots=True)
class Search:
    dense: DenseEncoder
    sparse: SparseEncoder
    index: VectorIndex

    async def __call__(self, query: SearchQuery) -> list[SearchHit]:
        sparse = await self.sparse.query(query.text, query.lang)
        try:
            dense = await self.dense.query(query.text)
        except Exception:
            log.warning("dense encoder failed; searching with BM25 only")
            dense = None
        return await self.index.search(query, dense, sparse)


def writer(dense: DenseEncoder, sparse: SparseEncoder, index: VectorIndex) -> _Writer:
    return _Writer(dense, sparse, index)


@dataclass(frozen=True, slots=True)
class SearchUseCases:
    index_entry: IndexEntry
    reindex: Reindex
    search: Search
