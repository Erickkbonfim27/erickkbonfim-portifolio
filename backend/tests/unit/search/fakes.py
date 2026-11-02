"""Deterministic stand-ins for the fastembed models: word hashing, no downloads."""

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence

from portfolio.contexts.search.application.ports import DenseVector
from portfolio.contexts.search.domain.model import SparseVector

DIMENSION = 32


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _bucket(word: str, size: int) -> int:
    return int(hashlib.sha256(word.encode()).hexdigest(), 16) % size


class HashingDense:
    """Bag of hashed words, normalized: texts sharing words point the same way."""

    def __init__(self) -> None:
        self.fail = False
        self.calls = 0

    @property
    def dimension(self) -> int:
        return DIMENSION

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSION
        for word in _words(text):
            vector[_bucket(word, DIMENSION)] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def documents(self, texts: Sequence[str]) -> list[DenseVector]:
        self.calls += 1
        return [self._embed(t) for t in texts]

    async def query(self, text: str) -> DenseVector:
        if self.fail:
            raise ConnectionError("model unavailable")
        return self._embed(text)


class HashingSparse:
    def __init__(self) -> None:
        self.langs: list[str] = []

    def _encode(self, text: str) -> SparseVector:
        counts = Counter(_bucket(word, 100_000) for word in _words(text))
        indices = tuple(sorted(counts))
        return SparseVector(indices, tuple(float(counts[i]) for i in indices))

    async def documents(self, texts: Sequence[str], lang: str) -> list[SparseVector]:
        self.langs.append(lang)
        return [self._encode(t) for t in texts]

    async def query(self, text: str, lang: str) -> SparseVector:
        return self._encode(text)
