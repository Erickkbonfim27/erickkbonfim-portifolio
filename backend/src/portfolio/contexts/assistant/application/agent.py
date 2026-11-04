"""The site's agent: Aeva's loop, run by LangGraph.

    route → prefetch → model ⇄ tools → guard → grounding → answer
                         ↘ off topic: the site's own reply
                                         ↘ rewrite → guard → grounding → answer | trim

LangGraph runs the graph; every decision is a pure function in `domain/` (route,
budget, guard, evidence). Each node reports a step as it finishes, so the site can
show the trajectory while the answer is being made.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from portfolio.contexts.assistant.application.ports import (
    AgentRun,
    AgentTracer,
    ChatModel,
    Experiment,
    Generation,
    Knowledge,
    Lookup,
    Message,
    ModelReply,
    StepRecord,
    Tier,
    ToolCall,
    ToolSpec,
)
from portfolio.contexts.assistant.domain import guard, prompts
from portfolio.contexts.assistant.domain.budget import Budget, Meter, StopReason
from portfolio.contexts.assistant.domain.evidence import Ledger, normalize_citations, render
from portfolio.contexts.assistant.domain.route import Mode, route

log = logging.getLogger(__name__)

MAX_HISTORY = 6
MAX_REWRITES = 1
PREFETCH = 5

TOOLS = (
    ToolSpec(
        "search_portfolio",
        "Hybrid search over everything published on Erick's site. Returns numbered passages.",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A short search query"}},
            "required": ["query"],
        },
    ),
    ToolSpec(
        "read_case",
        "The full text of one case study, by its slug (e.g. vizzion, loopia, rhye, silpi).",
        {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    ),
)


@dataclass(frozen=True, slots=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class Event:
    """What the site receives while the answer is made: steps, then the answer."""

    kind: Literal["step", "answer", "error"]
    data: dict[str, Any]


class _State(TypedDict, total=False):
    messages: list[Message]
    answer: str
    verdict: guard.Verdict
    rewrites: int
    stop: str
    mode: Mode
    unsupported: list[str]  # claims the grounding check could not find in the passages


@dataclass
class _Run:
    """Everything one answer accumulates; lives for one call."""

    question: str
    lang: str
    meter: Meter
    clock: Callable[[], float]
    emit: Callable[[Event], None]
    ledger: Ledger = field(default_factory=Ledger)
    steps: list[StepRecord] = field(default_factory=list)
    generations: list[Generation] = field(default_factory=list)

    def ms(self, since: float) -> float:
        return round((self.clock() - since) * 1000, 1)

    def step(self, name: str, begin: float, detail: dict[str, Any]) -> None:
        record = StepRecord(
            name, round((begin - self.meter.started) * 1000, 1), self.ms(begin), detail
        )
        self.steps.append(record)
        self.emit(Event("step", {"name": name, "ms": record.ms, "detail": detail}))


@dataclass(frozen=True, slots=True)
class Agent:
    model: ChatModel
    knowledge: Knowledge
    budget: Budget = field(default_factory=Budget)
    tracer: AgentTracer | None = None
    clock: Callable[[], float] = field(default=time.perf_counter)
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    async def stream(
        self,
        question: str,
        history: Sequence[Turn],
        lang: str,
        *,
        trace: str | None = None,
        tags: Sequence[str] = (),
        experiment: Experiment | None = None,
    ) -> AsyncGenerator[Event]:
        """Steps as they finish, then the answer. `trace` names the run's trace, for a
        caller that links it (the evals); otherwise each run gets a new one."""
        events: asyncio.Queue[Event | None] = asyncio.Queue()
        task = asyncio.create_task(
            self._run(
                question,
                history,
                lang,
                events.put_nowait,
                trace=trace or uuid4().hex,
                tags=tags,
                experiment=experiment,
            )
        )
        task.add_done_callback(lambda _: events.put_nowait(None))
        try:
            while (event := await events.get()) is not None:
                yield event
            await task  # surfaces an unexpected error after the queue drains
        finally:
            task.cancel()

    async def _run(
        self,
        question: str,
        history: Sequence[Turn],
        lang: str,
        emit: Callable[[Event], None],
        *,
        trace: str,
        tags: Sequence[str],
        experiment: Experiment | None,
    ) -> None:
        started_at = self.now()
        run = _Run(question, lang, Meter(self.budget, self.clock()), self.clock, emit)
        system = prompts.load("system")
        messages = [Message("system", system.fill(lang=lang))]
        messages += [Message(t.role, t.content) for t in history[-MAX_HISTORY:]]
        messages.append(Message("user", question))
        try:
            final = await self._graph(run).ainvoke({"messages": messages, "rewrites": 0})
        except Exception:
            log.exception("assistant: the answer failed")
            emit(Event("error", {"message": "the assistant failed"}))
            return
        answer = final.get("answer", "")
        cited = run.ledger.cited(answer)
        meter = run.meter
        emit(
            Event(
                "answer",
                {
                    "text": answer,
                    "citations": [
                        {
                            "n": c.n,
                            "title": c.passage.title,
                            "heading": c.passage.heading,
                            "kind": c.passage.kind,
                            "slug": c.passage.slug,
                        }
                        for c in cited
                    ],
                    "stop": final.get("stop", StopReason.ANSWERED),
                    "usage": {
                        "input_tokens": meter.input_tokens,
                        "output_tokens": meter.output_tokens,
                        "cost": round(meter.cost, 6),
                        "ms": run.ms(meter.started),
                    },
                },
            )
        )
        if self.tracer is not None:
            self.tracer.record(
                AgentRun(
                    question,
                    lang,
                    started_at,
                    run.steps,
                    run.generations,
                    answer,
                    str(final.get("stop", StopReason.ANSWERED)),
                    [
                        system.version,
                        prompts.load("rewrite").version,
                        prompts.load("grounding").version,
                    ],
                    trace,
                    tags,
                    experiment,
                )
            )

    def _graph(self, run: _Run) -> Any:
        return _Nodes(self, run).compile()

    async def _call(
        self,
        run: _Run,
        name: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        tier: Tier,
    ) -> ModelReply:
        begin = self.clock()
        reply = await self.model.complete(messages, tools, tier)
        run.meter.rounds += 1
        run.meter.input_tokens += reply.usage.input_tokens
        run.meter.output_tokens += reply.usage.output_tokens
        run.meter.cost += reply.usage.cost
        run.generations.append(
            Generation(
                name,
                reply.model,
                round((begin - run.meter.started) * 1000, 1),
                run.ms(begin),
                list(messages),
                reply.text,
                reply.usage,
            )
        )
        return reply

    async def _tool(self, run: _Run, call: ToolCall) -> tuple[str, dict[str, Any]]:
        try:
            args = json.loads(call.arguments or "{}")
        except ValueError:
            return "The arguments were not valid JSON.", {"error": "invalid arguments"}
        try:
            async with asyncio.timeout(self.budget.tool_timeout_seconds):
                if call.name == "search_portfolio" and isinstance(args.get("query"), str):
                    query = args["query"][:200]
                    lookup = await self.knowledge.search(query, run.lang, PREFETCH)
                    cited = run.ledger.add(lookup.passages)
                    return render(cited), _search_detail(query, lookup, cited)
                if call.name == "read_case" and isinstance(args.get("slug"), str):
                    passage = await self.knowledge.case(args["slug"][:80], run.lang)
                    if passage is None:
                        return f"No case study called {args['slug']!r}.", {
                            "slug": args["slug"],
                            "found": [],
                        }
                    cited = run.ledger.add([passage])
                    return render(cited, max_chars=6000), {
                        "slug": args["slug"],
                        "found": _found(cited),
                    }
        except TimeoutError:
            return "The lookup took too long.", {"error": "timeout"}
        return f"Unknown tool or arguments: {call.name}.", {"error": "unknown tool"}


class _Nodes:
    """The graph's nodes for one answer. Decisions are domain functions; nodes wire them."""

    def __init__(self, agent: "Agent", run: _Run) -> None:
        self.agent = agent
        self.run = run

    async def route_node(self, state: _State) -> _State:
        begin = self.agent.clock()
        decided = route(self.run.question)
        self.run.step("route", begin, {"mode": decided.mode.value, "reason": decided.reason})
        return {"mode": decided.mode}

    async def prefetch_node(self, state: _State) -> _State:
        begin = self.agent.clock()
        lookup = await self.agent.knowledge.search(self.run.question, self.run.lang, PREFETCH)
        # Who Erick is, always: identity should not depend on how a question ranks.
        try:
            profile = await self.agent.knowledge.profile(self.run.lang)
        except Exception:  # the search alone still answers
            log.warning("assistant: profile not read", exc_info=True)
            profile = None
        cited = self.run.ledger.add([*([profile] if profile else []), *lookup.passages])
        self.run.step("retrieve", begin, _search_detail(self.run.question, lookup, cited))
        note = Message("system", f"Passages for this question:\n\n{render(cited)}")
        return {"messages": [*state["messages"], note]}

    async def model_node(self, state: _State) -> _State:
        begin = self.agent.clock()
        stop = self.run.meter.exhausted(self.agent.clock())
        messages = state["messages"]
        tools: Sequence[ToolSpec] = TOOLS if state.get("mode") is Mode.TOOLS else ()
        if stop is not None:
            tools = ()
            messages = [*messages, Message("system", prompts.load("synthesis").text)]
        reply = await self.agent._call(self.run, "model", messages, tools, "fast")
        detail = {
            "model": reply.model,
            "input_tokens": reply.usage.input_tokens,
            "output_tokens": reply.usage.output_tokens,
            "tool_calls": [call.name for call in reply.calls],
        }
        off_topic = not reply.calls and prompts.is_off_topic(reply.text)
        if off_topic:
            detail["off_topic"] = True
        self.run.step("model", begin, detail)
        if reply.calls and stop is None:
            return {"messages": [*messages, Message("assistant", reply.text, reply.calls)]}
        if off_topic:
            lang = self.run.lang if self.run.lang in prompts.OFF_TOPIC else "en"
            return {
                "messages": messages,
                "answer": prompts.OFF_TOPIC[lang],
                "stop": StopReason.OFF_TOPIC.value,
            }
        return {
            "messages": messages,
            "answer": normalize_citations(reply.text),
            "stop": (stop or StopReason.ANSWERED).value,
        }

    async def tools_node(self, state: _State) -> _State:
        messages = list(state["messages"])
        for call in messages[-1].calls:
            begin = self.agent.clock()
            if self.run.meter.tool_calls >= self.agent.budget.max_tool_calls:
                content, detail = (
                    "Skipped: no more lookups for this question.",
                    {"skipped": True},
                )
            else:
                self.run.meter.tool_calls += 1
                content, detail = await self.agent._tool(self.run, call)
            self.run.step(f"tool.{call.name}", begin, detail)
            messages.append(Message("tool", content, tool_call_id=call.id))
        return {"messages": messages}

    async def guard_node(self, state: _State) -> _State:
        begin = self.agent.clock()
        # The answer may rely on the passages, and on what the visitor said in the question.
        verdict = guard.check(
            state.get("answer", ""),
            f"{self.run.ledger.text()}\n{self.run.question}",
            passages=len(self.run.ledger),
            allowed_emails=frozenset({guard.OWNER_EMAIL}),
        )
        self.run.step("guard", begin, {"passed": verdict.passed, "reasons": verdict.reasons})
        return {"verdict": verdict}

    async def grounding_node(self, state: _State) -> _State:
        """A second reading, by the model, claim by claim, against the passages."""
        begin = self.agent.clock()
        answer = state.get("answer", "")
        # Every passage found: a claim may stand on one the answer forgot to cite.
        checked = self.run.ledger.cited_all()
        messages = [
            Message("system", prompts.load("grounding").text),
            Message(
                "user",
                f"Passages:\n\n{render(checked, max_chars=6000)}\n\nAnswer to check:\n\n{answer}",
            ),
        ]
        # A model without long reasoning: the check is a list, and it must be quick.
        reply = await self.agent._call(self.run, "grounding", messages, (), "strong")
        unsupported = guard.parse_grounding(reply.text)
        if unsupported is not None:
            sources = f"{self.run.ledger.text()}\n{self.run.question}"
            unsupported = [
                claim
                for claim in unsupported
                if not guard.is_meta(claim) and not guard.supported(claim, sources)
            ]
        detail: dict[str, Any] = {"model": reply.model, "passages": [c.n for c in checked]}
        if unsupported is None:
            # An unreadable verdict does not block the answer: the code checks already passed.
            detail.update(passed=True, unreadable=True)
            unsupported = []
        else:
            detail.update(passed=not unsupported, unsupported=unsupported)
        verdict = guard.Verdict(
            not unsupported, [f"not supported by the passages: {c}" for c in unsupported]
        )
        self.run.step("grounding", begin, detail)
        return {"verdict": verdict, "unsupported": unsupported}

    async def rewrite_node(self, state: _State) -> _State:
        begin = self.agent.clock()
        note = prompts.load("rewrite").fill(reasons="; ".join(state["verdict"].reasons))
        messages = [
            *state["messages"],
            Message("assistant", state.get("answer", "")),
            Message("user", note),
        ]
        # The strong model: an edit that must remove exactly what was flagged, and no more.
        reply = await self.agent._call(self.run, "rewrite", messages, (), "strong")
        self.run.step("rewrite", begin, {"reasons": state["verdict"].reasons})
        return {"answer": normalize_citations(reply.text), "rewrites": state.get("rewrites", 0) + 1}

    async def trim_node(self, state: _State) -> _State:
        """Still flagged after a rewrite: drop the flagged sentences, keep the prose. With too
        little left, point to Erick rather than show passages."""
        begin = self.agent.clock()
        answer = state.get("answer", "")
        trimmed = guard.trim(
            answer,
            f"{self.run.ledger.text()}\n{self.run.question}",
            passages=len(self.run.ledger),
            unsupported=state.get("unsupported", []),
            allowed_emails=frozenset({guard.OWNER_EMAIL}),
        )
        lang = self.run.lang if self.run.lang in prompts.FALLBACK else "en"
        self.run.step(
            "trim",
            begin,
            {
                "reasons": state["verdict"].reasons,
                "kept": len(trimmed),
                "removed": len(answer) - len(trimmed),
            },
        )
        return {"answer": trimmed or prompts.FALLBACK[lang]}

    @staticmethod
    def after_route(state: _State) -> str:
        return "prefetch" if state["mode"] is Mode.TOOLS else "model"

    @staticmethod
    def after_model(state: _State) -> str:
        if state.get("stop") == StopReason.OFF_TOPIC:
            return END  # the site's own words: nothing to check
        return "guard" if "answer" in state else "tools"

    @staticmethod
    def after_guard(state: _State) -> str:
        if state["verdict"].passed:
            # Small talk has nothing to check against; anything else gets a second reading.
            return "grounding" if state.get("mode") is Mode.TOOLS else END
        return "rewrite" if state.get("rewrites", 0) < MAX_REWRITES else "trim"

    @staticmethod
    def after_grounding(state: _State) -> str:
        if state["verdict"].passed:
            return END
        return "rewrite" if state.get("rewrites", 0) < MAX_REWRITES else "trim"

    def compile(self) -> Any:
        graph = StateGraph(_State)
        graph.add_node("route", self.route_node)
        graph.add_node("prefetch", self.prefetch_node)
        graph.add_node("model", self.model_node)
        graph.add_node("tools", self.tools_node)
        graph.add_node("guard", self.guard_node)
        graph.add_node("rewrite", self.rewrite_node)
        graph.add_node("trim", self.trim_node)
        graph.add_edge(START, "route")
        graph.add_conditional_edges("route", self.after_route, ["prefetch", "model"])
        graph.add_edge("prefetch", "model")
        graph.add_conditional_edges("model", self.after_model, [END, "guard", "tools"])
        graph.add_edge("tools", "model")
        graph.add_node("grounding", self.grounding_node)
        graph.add_conditional_edges(
            "guard", self.after_guard, [END, "grounding", "rewrite", "trim"]
        )
        graph.add_conditional_edges("grounding", self.after_grounding, [END, "rewrite", "trim"])
        graph.add_edge("rewrite", "guard")
        graph.add_edge("trim", END)
        return graph.compile()


def _search_detail(query: str, lookup: Lookup, cited: Sequence[Any]) -> dict[str, Any]:
    """A search as the trajectory shows it: its inner steps, each ranking, the result."""
    return {
        "query": query,
        "steps": [{"name": name, "ms": ms} for name, ms in lookup.steps],
        "dense": [
            {"title": r.title, "heading": r.heading, "score": round(r.score, 3)}
            for r in lookup.dense
        ],
        "sparse": [
            {"title": r.title, "heading": r.heading, "score": round(r.score, 3)}
            for r in lookup.sparse
        ],
        "found": _found(cited),
    }


def _found(cited: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "n": c.n,
            "title": c.passage.title,
            "heading": c.passage.heading,
            "score": round(c.passage.score, 3),
        }
        for c in cited
    ]
