"""How much one answer may spend: model rounds, tool calls, time and tokens.

The meter is checked before every model call. When a limit is reached the agent
gets one last call without tools, to answer with what it has.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class StopReason(StrEnum):
    ANSWERED = "answered"
    ROUNDS = "rounds"
    TOOL_CALLS = "tool_calls"
    TIME = "time"
    TOKENS = "tokens"
    OFF_TOPIC = "off_topic"  # not about Erick: the site's own reply, nothing to check


@dataclass(frozen=True, slots=True)
class Budget:
    max_rounds: int = 4
    max_tool_calls: int = 5
    max_seconds: float = 30.0
    max_input_tokens: int = 30_000
    tool_timeout_seconds: float = 8.0


@dataclass(slots=True)
class Meter:
    budget: Budget
    started: float
    rounds: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    log: list[str] = field(default_factory=list)

    def exhausted(self, now: float) -> StopReason | None:
        if self.rounds >= self.budget.max_rounds:
            return StopReason.ROUNDS
        if self.tool_calls >= self.budget.max_tool_calls:
            return StopReason.TOOL_CALLS
        if now - self.started >= self.budget.max_seconds:
            return StopReason.TIME
        if self.input_tokens >= self.budget.max_input_tokens:
            return StopReason.TOKENS
        return None
