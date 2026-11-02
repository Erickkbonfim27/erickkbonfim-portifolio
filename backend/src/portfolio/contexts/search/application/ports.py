from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from portfolio.contexts.search.domain.model import (
    Chunk,
    SearchHit,
    SearchQuery,
    SourceDocument,
    SparseVector,
)

DenseVector = Sequence[float]


class SourceCatalog(Protocol):
    """Published content as plain text. Implemented over the content context."""

    async def entry(self, entry_id: UUID) -> list[SourceDocument]:
        """Every language of the entry; empty when it is not published."""
        ...

    async def everything(self) -> list[SourceDocument]: ...


class DenseEncoder(Protocol):
    @property
    def dimension(self) -> int: ...

    async def documents(self, texts: Sequence[str]) -> list[DenseVector]: ...
    async def query(self, text: str) -> DenseVector: ...


class SparseEncoder(Protocol):
    """BM25 with a stemmer per language: Portuguese and English stem differently."""

    async def documents(self, texts: Sequence[str], lang: str) -> list[SparseVector]: ...
    async def query(self, text: str, lang: str) -> SparseVector: ...


class VectorIndex(Protocol):
    async def ensure(self, dimension: int) -> None:
        """Create the collection if it does not exist."""
        ...

    async def recreate(self, dimension: int) -> None: ...

    async def upsert(
        self,
        chunks: Sequence[Chunk],
        dense: Sequence[DenseVector],
        sparse: Sequence[SparseVector],
    ) -> None: ...

    async def delete_entry(self, entry_id: UUID, keep: Sequence[UUID] = ()) -> None:
        """Remove the entry's chunks, except those in `keep` (the ones just written)."""
        ...

    async def search(
        self, query: SearchQuery, dense: DenseVector | None, sparse: SparseVector
    ) -> list[SearchHit]:
        """Hybrid when `dense` is given (fused by rank), BM25 only otherwise."""
        ...
