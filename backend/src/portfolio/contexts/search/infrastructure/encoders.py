"""Encoders running in-process with fastembed (ONNX, CPU).

Models are loaded on first use, not at import, so the API starts fast and a
process that never searches never pays the ~500 MB. Inference runs in a thread
to keep the event loop free.
"""

import asyncio
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Protocol

from portfolio.contexts.search.application.ports import DenseVector
from portfolio.contexts.search.domain.model import SparseVector

DEFAULT_DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BM25_MODEL = "Qdrant/bm25"
# Snowball stemmer names used by fastembed's BM25.
STEMMER_LANGUAGE = {"en": "english", "pt": "portuguese"}


class _DenseModel(Protocol):
    def embed(self, documents: Iterable[str], **kwargs: Any) -> Iterable[Any]: ...
    def query_embed(self, query: str, **kwargs: Any) -> Iterable[Any]: ...


class _SparseModel(Protocol):
    def embed(self, documents: Iterable[str], **kwargs: Any) -> Iterable[Any]: ...
    def query_embed(self, query: str, **kwargs: Any) -> Iterable[Any]: ...


class _Lazy[T]:
    """Builds the value once, on first use, safely across threads."""

    def __init__(self, build: Callable[[], T]) -> None:
        self._build = build
        self._value: T | None = None
        self._lock = threading.Lock()

    def get(self) -> T:
        # A lock on every call costs nothing next to a model inference.
        with self._lock:
            if self._value is None:
                self._value = self._build()
            return self._value


def _fastembed_dense(model: str, cache_dir: str | None) -> _DenseModel:  # pragma: no cover
    from fastembed import TextEmbedding  # noqa: PLC0415 - heavy import, only when used

    return TextEmbedding(model, cache_dir=cache_dir)


def _fastembed_bm25(language: str, cache_dir: str | None) -> _SparseModel:  # pragma: no cover
    from fastembed import SparseTextEmbedding  # noqa: PLC0415

    return SparseTextEmbedding(BM25_MODEL, cache_dir=cache_dir, language=language)


class FastembedDense:
    def __init__(
        self,
        dimension: int,
        build: Callable[[], _DenseModel],
    ) -> None:
        self._dimension = dimension
        self._model = _Lazy(build)

    @classmethod
    def create(cls, model: str, dimension: int, cache_dir: str | None) -> "FastembedDense":
        return cls(dimension, lambda: _fastembed_dense(model, cache_dir))

    @property
    def dimension(self) -> int:
        return self._dimension

    async def documents(self, texts: Sequence[str]) -> list[DenseVector]:
        def run() -> list[DenseVector]:
            return [vector.tolist() for vector in self._model.get().embed(list(texts))]

        return await asyncio.to_thread(run)

    async def query(self, text: str) -> DenseVector:
        def run() -> DenseVector:
            return list(next(iter(self._model.get().query_embed(text))).tolist())

        return await asyncio.to_thread(run)


def _sparse(embedding: Any) -> SparseVector:
    return SparseVector(
        indices=tuple(int(i) for i in embedding.indices),
        values=tuple(float(v) for v in embedding.values),
    )


class FastembedBm25:
    def __init__(self, build: Callable[[str], _SparseModel]) -> None:
        def lazy(language: str) -> _Lazy[_SparseModel]:
            return _Lazy(lambda: build(language))

        self._models = {lang: lazy(language) for lang, language in STEMMER_LANGUAGE.items()}

    @classmethod
    def create(cls, cache_dir: str | None) -> "FastembedBm25":
        return cls(lambda language: _fastembed_bm25(language, cache_dir))

    async def documents(self, texts: Sequence[str], lang: str) -> list[SparseVector]:
        model = self._models[lang]
        return await asyncio.to_thread(lambda: [_sparse(e) for e in model.get().embed(list(texts))])

    async def query(self, text: str, lang: str) -> SparseVector:
        model = self._models[lang]
        return await asyncio.to_thread(lambda: _sparse(next(iter(model.get().query_embed(text)))))
