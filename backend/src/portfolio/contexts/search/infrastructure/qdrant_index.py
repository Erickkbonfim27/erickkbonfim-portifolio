"""Hybrid index in Qdrant: one dense vector and one BM25 sparse vector per chunk.

Search runs both and fuses the two rankings with Reciprocal Rank Fusion inside
Qdrant (Query API), so neither score scale has to be calibrated against the other.
"""

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from portfolio.contexts.search.application.ports import DenseVector
from portfolio.contexts.search.domain.model import Chunk, SearchHit, SearchQuery, SparseVector

DENSE = "dense"
SPARSE = "bm25"
# Each branch of the hybrid search brings this many candidates per final result.
PREFETCH_FACTOR = 4


def _sparse(vector: SparseVector) -> models.SparseVector:
    return models.SparseVector(indices=list(vector.indices), values=list(vector.values))


def _filter(query: SearchQuery) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(key="lang", match=models.MatchValue(value=query.lang))
    ]
    if query.kinds:
        must.append(models.FieldCondition(key="kind", match=models.MatchAny(any=list(query.kinds))))
    return models.Filter(must=must)


class QdrantIndex:
    def __init__(self, client: AsyncQdrantClient, collection: str) -> None:
        self._client = client
        self._collection = collection

    async def ensure(self, dimension: int) -> None:
        if not await self._client.collection_exists(self._collection):
            await self._create(dimension)

    async def recreate(self, dimension: int) -> None:
        if await self._client.collection_exists(self._collection):
            await self._client.delete_collection(self._collection)
        await self._create(dimension)

    async def _create(self, dimension: int) -> None:
        await self._client.create_collection(
            self._collection,
            vectors_config={
                DENSE: models.VectorParams(size=dimension, distance=models.Distance.COSINE)
            },
            # IDF computed by Qdrant over the collection: the BM25 encoder only
            # supplies term frequencies.
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field in ("lang", "kind", "entry_id"):
            await self._client.create_payload_index(
                self._collection, field, models.PayloadSchemaType.KEYWORD
            )

    async def upsert(
        self,
        chunks: Sequence[Chunk],
        dense: Sequence[DenseVector],
        sparse: Sequence[SparseVector],
    ) -> None:
        points = [
            models.PointStruct(
                id=str(chunk.id),
                vector={DENSE: list(d), SPARSE: _sparse(s)},
                payload={
                    "entry_id": str(chunk.entry_id),
                    "kind": chunk.kind,
                    "slug": chunk.slug,
                    "lang": chunk.lang,
                    "position": chunk.position,
                    "title": chunk.title,
                    "heading": chunk.heading,
                    "text": chunk.text,
                },
            )
            for chunk, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        await self._client.upsert(self._collection, points=points, wait=True)

    async def delete_entry(self, entry_id: UUID, keep: Sequence[UUID] = ()) -> None:
        if not await self._client.collection_exists(self._collection):
            return
        selector = models.Filter(
            must=[
                models.FieldCondition(key="entry_id", match=models.MatchValue(value=str(entry_id)))
            ],
            must_not=[models.HasIdCondition(has_id=[str(k) for k in keep])] if keep else None,
        )
        await self._client.delete(
            self._collection, points_selector=models.FilterSelector(filter=selector), wait=True
        )

    async def search(
        self, query: SearchQuery, dense: DenseVector | None, sparse: SparseVector
    ) -> list[SearchHit]:
        if not await self._client.collection_exists(self._collection):
            return []
        where = _filter(query)
        if dense is None:
            response = await self._client.query_points(
                self._collection,
                query=_sparse(sparse),
                using=SPARSE,
                query_filter=where,
                limit=query.limit,
            )
        else:
            candidates = query.limit * PREFETCH_FACTOR
            response = await self._client.query_points(
                self._collection,
                prefetch=[
                    models.Prefetch(query=list(dense), using=DENSE, filter=where, limit=candidates),
                    models.Prefetch(
                        query=_sparse(sparse), using=SPARSE, filter=where, limit=candidates
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=query.limit,
            )
        return _hits(response.points)

    async def rank(
        self,
        query: SearchQuery,
        using: Literal["dense", "sparse"],
        vector: DenseVector | SparseVector,
    ) -> list[SearchHit]:
        if not await self._client.collection_exists(self._collection):
            return []
        response = await self._client.query_points(
            self._collection,
            query=_sparse(vector) if isinstance(vector, SparseVector) else list(vector),
            using=SPARSE if using == "sparse" else DENSE,
            query_filter=_filter(query),
            limit=query.limit,
        )
        return _hits(response.points)


def _hits(points: Sequence[models.ScoredPoint]) -> list[SearchHit]:
    return [
        SearchHit(
            entry_id=UUID(str(payload["entry_id"])),
            kind=str(payload["kind"]),
            slug=str(payload["slug"]),
            title=str(payload["title"]),
            heading=str(payload["heading"]),
            text=str(payload["text"]),
            score=point.score,
        )
        for point in points
        if (payload := point.payload) is not None
    ]
