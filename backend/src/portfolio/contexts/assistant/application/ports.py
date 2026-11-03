from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from portfolio.contexts.assistant.domain.evidence import Passage

Tier = Literal["fast", "strong"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON, as the model wrote it


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0  # US$, as the provider reports it


@dataclass(frozen=True, slots=True)
class ModelReply:
    text: str
    calls: tuple[ToolCall, ...]
    usage: Usage
    model: str


class ChatModel(Protocol):
    async def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], tier: Tier
    ) -> ModelReply: ...


@dataclass(frozen=True, slots=True)
class Ranked:
    title: str
    heading: str
    score: float


@dataclass(frozen=True, slots=True)
class Lookup:
    """One search, with its inner steps, so the trajectory can show how it was found."""

    passages: list[Passage]
    steps: list[tuple[str, float]] = field(default_factory=list)  # (step, milliseconds)
    dense: list[Ranked] = field(default_factory=list)
    sparse: list[Ranked] = field(default_factory=list)


class Knowledge(Protocol):
    """What the agent can read: the site's own published content."""

    async def search(self, query: str, lang: str, limit: int) -> Lookup: ...
    async def case(self, slug: str, lang: str) -> Passage | None: ...
    async def profile(self, lang: str) -> Passage | None: ...


@dataclass(frozen=True, slots=True)
class StepRecord:
    name: str
    start_ms: float
    ms: float
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Generation:
    """One model call, for the trace."""

    name: str
    model: str
    start_ms: float
    ms: float
    messages: Sequence[Message]
    output: str
    usage: Usage


@dataclass(frozen=True, slots=True)
class Experiment:
    """The eval run and dataset item an answer belongs to, so the trace joins them."""

    id: str
    name: str
    dataset_id: str
    item_id: str
    expected: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentRun:
    question: str
    lang: str
    started_at: datetime
    steps: Sequence[StepRecord]
    generations: Sequence[Generation]
    answer: str
    stop: str
    prompts: Sequence[str]
    trace_id: str = ""  # 32 hex, chosen by the caller when it links the trace (evals)
    tags: Sequence[str] = ()
    experiment: Experiment | None = None


class AgentTracer(Protocol):
    def record(self, run: AgentRun) -> None:
        """Hand the run to the tracing backend. Must not block nor raise."""
        ...
