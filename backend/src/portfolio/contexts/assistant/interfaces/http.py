"""`POST /api/chat`: the site's agent, streamed as Server-Sent Events.

Events: `step` (a node finished: name, ms, detail), then `answer` (text, citations,
usage) or `error`. Steps, not tokens: the guard must see the whole answer first.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from portfolio.contexts.assistant.application.agent import Agent, Event, Turn

MAX_MESSAGE = 800
MAX_TURN = 2000
MAX_TURNS = 6
PER_MINUTE = 20
PER_DAY = 150
MINUTE = timedelta(minutes=1)
DAY = timedelta(days=1)


class Limiter(Protocol):
    async def hit(self, bucket: str, key: str, limit: int, window: timedelta) -> bool: ...


class DailySpend:
    """A global cap on what the model may cost per day, kept in process memory.

    One API process serves the site; a restart resets the day's count, which errs
    on the side of answering.
    """

    def __init__(self, cap_usd: float) -> None:
        self.cap = cap_usd
        self._day = date.min
        self._spent = 0.0

    def _today(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day, self._spent = today, 0.0

    def allows(self) -> bool:
        self._today()
        return self._spent < self.cap

    def add(self, cost: float) -> None:
        self._today()
        self._spent += cost


@dataclass(frozen=True, slots=True)
class Assistant:
    agent: Agent
    limiter: Limiter
    spend: DailySpend


def _assistant(request: Request) -> Assistant:
    return cast(Assistant, request.app.state.assistant)


AssistantDep = Annotated[Assistant, Depends(_assistant)]

router = APIRouter(prefix="/api", tags=["portfolio"])


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_TURN)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)
    history: list[TurnIn] = Field(default_factory=list, max_length=MAX_TURNS * 2)
    lang: Literal["en", "pt"] = "en"


def _sse(event: Event) -> str:
    return f"event: {event.kind}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/chat", response_class=StreamingResponse)
async def chat(body: ChatIn, request: Request, assistant: AssistantDep) -> StreamingResponse:
    """Ask the site's agent about Erick's work. Streams each step, then the answer,
    with citations to the published pages it used."""
    client = request.client.host if request.client else "unknown"
    if not await assistant.limiter.hit("chat-minute", client, PER_MINUTE, MINUTE) or not (
        await assistant.limiter.hit("chat-day", client, PER_DAY, DAY)
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many questions; try later")
    if not assistant.spend.allows():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "the assistant is resting today")
    history = [Turn(turn.role, turn.content) for turn in body.history][-MAX_TURNS:]

    async def events() -> AsyncIterator[str]:
        try:
            async for event in assistant.agent.stream(body.message.strip(), history, body.lang):
                if event.kind == "answer":
                    assistant.spend.add(float(event.data["usage"]["cost"]))
                yield _sse(event)
        except Exception:
            yield _sse(Event("error", {"message": "the assistant failed"}))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
