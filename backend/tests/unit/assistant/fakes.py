import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from portfolio.contexts.assistant.application.ports import (
    Lookup,
    Message,
    ModelReply,
    Ranked,
    Tier,
    ToolCall,
    ToolSpec,
    Usage,
)
from portfolio.contexts.assistant.domain import prompts
from portfolio.contexts.assistant.domain.evidence import Passage

P1 = Passage("project", "vizzion", "Vizzion", "Integrations", "We integrated 150 sources.", 0.9)
P2 = Passage("experience", "loopia", "Loopia", "", "Langfuse traces for the agents.", 0.7)
PROFILE = Passage("profile", "profile", "Erick", "Engineer", "Software and AI engineer.", 1.0)


def say(text: str, cost: float = 0.001) -> ModelReply:
    return ModelReply(text, (), Usage(100, 20, cost), "fake/model")


def call(name: str, arguments: str, id_: str = "c1") -> ModelReply:
    return ModelReply("", (ToolCall(id_, name, arguments),), Usage(100, 5, 0.0005), "fake/model")


SUPPORTED = say('{"unsupported": []}')


@dataclass
class ScriptedModel:
    """Answers with the replies it was given, in order, and remembers what it was asked.

    The grounding check gets its own queue, `verdicts`, so a test scripts the answer and
    the verdict on it separately; with none left, everything is supported."""

    replies: list[ModelReply] = field(default_factory=list)
    verdicts: list[ModelReply] = field(default_factory=list)
    seen: list[tuple[list[Message], list[str], Tier]] = field(default_factory=list)
    fail: bool = False

    async def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], tier: Tier
    ) -> ModelReply:
        if self.fail:
            raise RuntimeError("provider down")
        if messages and messages[0].content == prompts.load("grounding").text:
            return self.verdicts.pop(0) if self.verdicts else SUPPORTED
        self.seen.append((list(messages), [t.name for t in tools], tier))
        return self.replies.pop(0) if self.replies else say("Nothing more to say.")


@dataclass
class FakeKnowledge:
    delay: float = 0.0
    queries: list[str] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=lambda: [P1, P2])
    profile_passage: Passage | None = PROFILE

    async def search(self, query: str, lang: str, limit: int) -> Lookup:
        await asyncio.sleep(self.delay)
        self.queries.append(query)
        if "nothing" in query:
            return Lookup([])
        return Lookup(
            self.passages,
            [("bm25.encode", 1.0), ("dense.encode", 90.0)],
            [Ranked("Vizzion", "Integrations", 0.8)],
            [Ranked("Loopia", "", 3.1)],
        )

    async def case(self, slug: str, lang: str) -> Passage | None:
        if slug != "rhye":
            return None
        return Passage("project", slug, slug.title(), "", "The full case.", 1.0)

    async def profile(self, lang: str) -> Passage | None:
        return self.profile_passage
