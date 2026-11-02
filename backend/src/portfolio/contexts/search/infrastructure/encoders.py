"""BM25 encoders running in-process with fastembed.

Loaded on first use, not at import, so the API starts fast. Encoding runs in a
thread to keep the event loop free. The dense side is an API (see `openrouter`).
"""

import asyncio
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Protocol

from portfolio.contexts.search.domain.model import SparseVector

BM25_MODEL = "Qdrant/bm25"
# Snowball stemmer names used by fastembed's BM25.
STEMMER_LANGUAGE = {"en": "english", "pt": "portuguese"}


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
        # A lock on every call costs nothing next to encoding.
        with self._lock:
            if self._value is None:
                self._value = self._build()
            return self._value


def _fastembed_bm25(language: str, cache_dir: str | None) -> _SparseModel:  # pragma: no cover
    from fastembed import SparseTextEmbedding  # noqa: PLC0415 - heavy import, only when used

    return SparseTextEmbedding(BM25_MODEL, cache_dir=cache_dir, language=language)


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
