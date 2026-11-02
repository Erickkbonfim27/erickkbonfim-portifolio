"""Dense embeddings from OpenRouter's embeddings API (OpenAI-compatible).

Only the dense side leaves the process: BM25 stays in fastembed, so when the
provider is slow or down, search keeps working on exact words (see `Search`).
"""

from collections.abc import Sequence
from typing import Any

import httpx

from portfolio.contexts.search.application.ports import DenseVector

BASE_URL = "https://openrouter.ai/api/v1"
# Inputs per request. Chunks are at most 1200 characters, so a batch stays far
# below the provider's per-request token limit.
BATCH_SIZE = 64
# A query has the BM25 fallback, so it gives up fast; indexing runs in the worker
# and can wait.
QUERY_TIMEOUT_SECONDS = 5.0
DOCUMENTS_TIMEOUT_SECONDS = 60.0


class EmbeddingError(RuntimeError):
    """The provider answered, but not with the embeddings that were asked for."""


class OpenRouterDense:
    def __init__(self, http: httpx.AsyncClient, model: str, dimension: int) -> None:
        self._http = http
        self._model = model
        self._dimension = dimension

    @classmethod
    def create(cls, api_key: str, model: str, dimension: int) -> "OpenRouterDense":
        http = httpx.AsyncClient(base_url=BASE_URL, headers={"Authorization": f"Bearer {api_key}"})
        return cls(http, model, dimension)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def documents(self, texts: Sequence[str]) -> list[DenseVector]:
        vectors: list[DenseVector] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            vectors.extend(await self._embed(batch, DOCUMENTS_TIMEOUT_SECONDS))
        return vectors

    async def query(self, text: str) -> DenseVector:
        [vector] = await self._embed([text], QUERY_TIMEOUT_SECONDS)
        return vector

    async def close(self) -> None:
        await self._http.aclose()

    async def _embed(self, texts: Sequence[str], seconds: float) -> list[DenseVector]:
        response = await self._http.post(
            "/embeddings",
            json={
                "model": self._model,
                "input": list(texts),
                # Asked for explicitly: the collection was created with this size.
                "dimensions": self._dimension,
                "encoding_format": "float",
            },
            timeout=seconds,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        # OpenRouter reports some provider failures as 200 with an error body.
        if "data" not in body:
            error = body.get("error") or {}
            raise EmbeddingError(f"no embeddings returned: {error.get('message', body)}")
        data = sorted(body["data"], key=lambda item: item["index"])
        if len(data) != len(texts):
            raise EmbeddingError(f"asked for {len(texts)} embeddings, got {len(data)}")
        vectors: list[DenseVector] = [[float(v) for v in item["embedding"]] for item in data]
        if any(len(v) != self._dimension for v in vectors):
            raise EmbeddingError(f"{self._model} did not return {self._dimension} dimensions")
        return vectors
