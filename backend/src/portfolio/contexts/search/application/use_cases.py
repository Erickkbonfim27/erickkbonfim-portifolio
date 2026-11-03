import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from portfolio.contexts.search.application.ports import (
    DenseEncoder,
    DenseVector,
    SearchRun,
    SearchTracer,
    SourceCatalog,
    SparseEncoder,
    Step,
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
        # Read first: if the database fails, the old index is still there to answer.
        documents = await self.catalog.everything()
        await self.writer.index.recreate(self.writer.dense.dimension)
        return len(await self.writer.write(documents))


@dataclass(frozen=True, slots=True)
class Explanation:
    """One search, step by step: what each ranking found and how long each step took."""

    hits: list[SearchHit]
    dense: list[SearchHit]
    sparse: list[SearchHit]
    steps: list[tuple[str, float]]  # (step, milliseconds), in order
    degraded: bool  # the dense side failed and BM25 answered alone


class _Timer:
    """Times the awaited steps of one run, from a common start."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._start = clock()
        self.steps: list[Step] = []

    async def __call__[T](self, name: str, work: Awaitable[T]) -> T:
        begin = self._clock()
        result = await work
        end = self._clock()
        self.steps.append(
            Step(name, round((begin - self._start) * 1000, 1), round((end - begin) * 1000, 1))
        )
        return result


@dataclass(frozen=True, slots=True)
class Search:
    dense: DenseEncoder
    sparse: SparseEncoder
    index: VectorIndex
    tracer: SearchTracer | None = None
    clock: Callable[[], float] = field(default=time.perf_counter)
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    async def __call__(self, query: SearchQuery) -> list[SearchHit]:
        started, timed = self.now(), _Timer(self.clock)
        sparse = await timed("bm25.encode", self.sparse.query(query.text, query.lang))
        dense = await timed("dense.encode", self._dense(query))
        hits = await timed("hybrid.search", self.index.search(query, dense, sparse))
        self._record(SearchRun("search", query, started, timed.steps, hits, dense is None))
        return hits

    async def explain(self, query: SearchQuery) -> Explanation:
        started, timed = self.now(), _Timer(self.clock)
        sparse = await timed("bm25.encode", self.sparse.query(query.text, query.lang))
        dense = await timed("dense.encode", self._dense(query))
        dense_hits = (
            await timed("dense.search", self.index.rank(query, "dense", dense))
            if dense is not None
            else []
        )
        sparse_hits = await timed("bm25.search", self.index.rank(query, "sparse", sparse))
        hits = await timed("rrf.fuse", self.index.search(query, dense, sparse))
        self._record(SearchRun("search.explain", query, started, timed.steps, hits, dense is None))
        return Explanation(
            hits,
            dense_hits,
            sparse_hits,
            [(step.name, step.ms) for step in timed.steps],
            degraded=dense is None,
        )

    def _record(self, run: SearchRun) -> None:
        if self.tracer is not None:
            self.tracer.record(run)

    async def _dense(self, query: SearchQuery) -> DenseVector | None:
        try:
            return await self.dense.query(query.text)
        except Exception:
            log.warning("dense encoder failed; searching with BM25 only")
            return None


def writer(dense: DenseEncoder, sparse: SparseEncoder, index: VectorIndex) -> _Writer:
    return _Writer(dense, sparse, index)


@dataclass(frozen=True, slots=True)
class SearchUseCases:
    index_entry: IndexEntry
    reindex: Reindex
    search: Search
