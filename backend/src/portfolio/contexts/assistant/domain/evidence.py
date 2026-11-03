"""What the agent found, numbered, so an answer can cite it as [1], [2]…"""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Passage:
    kind: str
    slug: str
    title: str
    heading: str
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class Cited:
    n: int
    passage: Passage


class Ledger:
    """Every passage the agent saw in this answer, in order, without duplicates."""

    def __init__(self) -> None:
        self._items: list[Passage] = []

    def add(self, passages: list[Passage]) -> list[Cited]:
        added = []
        for passage in passages:
            key = (passage.slug, passage.heading, passage.text[:80])
            known = next(
                (i for i, p in enumerate(self._items) if (p.slug, p.heading, p.text[:80]) == key),
                None,
            )
            if known is None:
                self._items.append(passage)
                known = len(self._items) - 1
            added.append(Cited(known + 1, self._items[known]))
        return added

    def __len__(self) -> int:
        return len(self._items)

    def text(self) -> str:
        return "\n".join(passage.text for passage in self._items)

    def cited_all(self) -> list[Cited]:
        return [Cited(n, passage) for n, passage in enumerate(self._items, start=1)]

    def cited(self, answer: str) -> list[Cited]:
        """The passages the answer points at with [n], in the order they first appear."""
        numbers: list[int] = []
        for match in re.finditer(r"\[(\d{1,2})\]", answer):
            n = int(match[1])
            if 1 <= n <= len(self._items) and n not in numbers:
                numbers.append(n)
        return [Cited(n, self._items[n - 1]) for n in numbers]


_NATIVE_CITATION = re.compile(r"[【\[]\s*(\d{1,2})\s*(?:†[^】\]]*)?[】\]]")


def normalize_citations(answer: str) -> str:
    """Citations as the site reads them, [1]. Some models write their own format,
    like 【1†L1-L3】; the number is kept, the rest dropped."""
    return _NATIVE_CITATION.sub(lambda m: f"[{m[1]}]", answer)


def render(cited: list[Cited], max_chars: int = 1600) -> str:
    """Passages as the model reads them."""
    blocks = []
    for item in cited:
        p = item.passage
        where = f"{p.title} · {p.heading}" if p.heading else p.title
        # The profile card is never cut: it is what every overview stands on.
        text = p.text if p.kind == "profile" else p.text[:max_chars]
        blocks.append(f"[{item.n}] {where} ({p.kind}/{p.slug})\n{text}")
    return "\n\n".join(blocks) if blocks else "No passages found."
