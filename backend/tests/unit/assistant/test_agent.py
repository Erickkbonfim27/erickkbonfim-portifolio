import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from portfolio.bridges import PROFILE_TTL_SECONDS, SiteKnowledge
from portfolio.contexts.assistant.application.agent import Agent, Event, Turn
from portfolio.contexts.assistant.application.ports import (
    AgentRun,
    Experiment,
    Generation,
    Lookup,
    Message,
    StepRecord,
    ToolSpec,
    Usage,
)
from portfolio.contexts.assistant.domain import guard, prompts
from portfolio.contexts.assistant.domain.budget import Budget, Meter, StopReason
from portfolio.contexts.assistant.domain.evidence import (
    Ledger,
    Passage,
    normalize_citations,
    render,
)
from portfolio.contexts.assistant.domain.route import Mode, route
from portfolio.contexts.assistant.infrastructure.openrouter import (
    ChatError,
    OpenRouterChat,
    arguments,
)
from portfolio.contexts.assistant.infrastructure.tracing import LangfuseAgentTracer, spans
from portfolio.contexts.assistant.interfaces.http import DailySpend
from portfolio.contexts.content.domain.kinds import Kind, Lang
from portfolio.platform.langfuse import Langfuse
from tests.unit.assistant.fakes import P1, P2, FakeKnowledge, ScriptedModel, call, say
from tests.unit.content.test_public import seed
from tests.unit.support import World, make_world

OWNER = frozenset({guard.OWNER_EMAIL})


class TestDomain:
    def test_budget_stops_on_each_limit(self) -> None:
        meter = Meter(
            Budget(max_rounds=2, max_tool_calls=2, max_seconds=10, max_input_tokens=100), 0
        )
        assert meter.exhausted(1) is None
        meter.input_tokens = 100
        assert meter.exhausted(1) is StopReason.TOKENS
        assert meter.exhausted(10) is StopReason.TIME
        meter.tool_calls = 2
        assert meter.exhausted(1) is StopReason.TOOL_CALLS
        meter.rounds = 2
        assert meter.exhausted(1) is StopReason.ROUNDS

    @pytest.mark.parametrize(
        "text",
        ["Oi!", "olá", "Thanks", "bom dia", "  HELLO  ", "Oi, tudo bem?", "hi! how are you?"],
    )
    def test_small_talk_goes_direct(self, text: str) -> None:
        assert route(text).mode is Mode.DIRECT

    def test_questions_use_tools(self) -> None:
        assert route("Oi, o Erick já usou Qdrant?").mode is Mode.TOOLS

    def test_ledger_numbers_dedupes_and_finds_citations(self) -> None:
        ledger = Ledger()
        assert [c.n for c in ledger.add([P1, P2])] == [1, 2]
        assert [c.n for c in ledger.add([P2])] == [2]
        assert len(ledger) == 2
        assert "150 sources" in ledger.text()
        assert [c.n for c in ledger.cited("Yes [2], and [1][2]. Not [9].")] == [2, 1]
        assert [c.n for c in ledger.cited_all()] == [1, 2]
        assert "[1] Vizzion · Integrations (project/vizzion)" in render(ledger.add([P1]))
        assert "[2] Loopia (experience/loopia)" in render(ledger.add([P2]))
        assert render([]) == "No passages found."

    def test_native_citations_become_brackets(self) -> None:
        assert normalize_citations("Yes【1†L1-L3】 and 【2】.") == "Yes[1] and [2]."

    def test_guard_numbers_names_citations_and_emails(self) -> None:
        sources = "We integrated 150 sources in 2024, about 1.200 rows, with an API and LangGraph."
        assert guard.check("It integrated 150 sources [1].", sources, passages=1).passed
        assert guard.check("Since 2024, with 3 people and 1.200 rows.", sources).passed
        assert guard.check("Two APIs, built with LangGraph [1].", sources, passages=1).passed
        bad = guard.check("It integrated 300 sources.", sources)
        assert bad.reasons == ["numbers not in the passages: 300"]
        names = guard.check("He used Kubernetes and PostGIS on GCP.", sources)
        assert names.reasons == ["names not in the passages: PostGIS, GCP"]
        assert guard.check("See [3].", sources, passages=1).reasons == [
            "citations to passages that do not exist"
        ]
        assert guard.check("", sources).reasons == ["empty answer"]
        assert "answer too long" in guard.check("a" * 2500, sources).reasons
        mail = guard.check(
            "Write to x@y.com or erickkbonfim@gmail.com", sources, allowed_emails=OWNER
        )
        assert mail.reasons == ["an email address that is not Erick's"]
        assert guard.check("Write to erickkbonfim@gmail.com.", sources, allowed_emails=OWNER).passed
        # A long answer without citations is the grounding check's call, not the guard's.
        assert guard.check("The site does not detail that. " * 6, sources, passages=2).passed

    def test_grounding_replies(self) -> None:
        assert guard.parse_grounding('ok {"unsupported": ["a", " "]}') == ["a"]
        assert guard.parse_grounding('{"unsupported": []}') == []
        assert guard.parse_grounding("no json") is None
        assert guard.parse_grounding("{broken") is None
        assert guard.parse_grounding('{"unsupported": [}') is None
        assert guard.parse_grounding('{"unsupported": "a"}') is None
        assert guard.parse_grounding("[1]") is None

    @pytest.mark.parametrize(
        ("claim", "meta"),
        [
            ("O site não traz informações sobre a tarifa horária.", True),
            ("use o formulário de contato", True),
            ("o e\u2011mail erickkbonfim@gmail.com", True),
            ("Ask Erick directly.", True),
            ("essa pergunta foge do que eu conheço do trabalho dele", True),
            ("writing code falls outside what I have about Erick's work", True),
            ("Além de Python, ele usa Rust", False),
            ("Ele trabalhou fora do Brasil", False),
            ("Erick has implemented RAG in production", False),
            ("O site não menciona, mas ele usou AWS", False),
            ("Ele integrou 300 fontes, o site não diz", False),
        ],
    )
    def test_what_is_not_a_claim_about_erick(self, claim: str, meta: bool) -> None:
        assert guard.is_meta(claim) is meta

    def test_vague_counts_fail_where_the_passages_give_a_number(self) -> None:
        sources = "We integrated 150 sources."
        verdict = guard.check("He integrated dozens of sources.", sources)
        assert verdict.reasons == ["a vague count instead of the passages' number: dozens"]
        assert guard.check("Hundreds of people [1].", "hundreds of people", passages=1).passed

    @pytest.mark.parametrize(
        ("claim", "held"),
        [
            ("foi cofundador e CTO da Vizzion (2024-2025) e da ConEng (2023-2024)", True),
            ("Ele é especializado em IA e LLMs", True),
            ("Erick tem experiência com LangGraph", True),
            ("trabalhou na Loopia como engenheiro de software", True),
            ("foi CTO da Loopia", False),
            ("integrações de centenas de fontes de dados", False),
            ("won a national award", False),
            ("não usou LangGraph", False),
            ("e", False),
        ],
    )
    def test_a_flag_on_what_a_line_says_is_dropped(self, claim: str, held: bool) -> None:
        sources = (
            "Erick: Engenheiro de software e IA, 22 anos, de Brusque, especializado em IA e LLMs.\n"
            "Carreira: Engenheiro de software, Loopia (2026-05 até 2026-10)\n"
            "Carreira: Cofundador & CTO, Vizzion (2024-03 até 2025-10)\n"
            "Carreira: Cofundador & CTO, ConEng (2023-09 até 2024-03)\n"
            "Agentes e ferramentas: LangGraph, tool calling. Integramos 150 fontes de dados."
        )
        assert guard.supported(claim, sources) is held

    def test_trim_keeps_the_sentences_that_hold(self) -> None:
        sources = "We integrated 150 sources with LangGraph."
        answer = (
            "Erick integrated 150 sources [1]. He used Kubernetes and PostGIS too. "
            "He wrote to x@y.com. See also [7]. He won a national award.\n"
            "He built the agents with LangGraph, as the case shows [1]."
        )
        trimmed = guard.trim(
            answer,
            sources,
            passages=1,
            unsupported=["won a national award"],
            allowed_emails=OWNER,
        )
        assert trimmed == (
            "Erick integrated 150 sources [1]. He built the agents with LangGraph, as the case "
            "shows [1]."
        )
        assert guard.trim("He used PostGIS.", sources, passages=1, unsupported=[]) == ""
        assert guard.trim("Short [1].", sources, passages=1, unsupported=["   "]) == ""

    def test_prompts_are_versioned_by_content(self) -> None:
        system = prompts.load("system")
        assert system.version.startswith("system@")
        assert len(system.version) == len("system@") + 12
        assert "pt" in system.fill(lang="pt")
        assert "{lang}" not in system.fill(lang="pt")
        assert set(prompts.FALLBACK) == {"en", "pt"}


class Recorder:
    def __init__(self) -> None:
        self.runs: list[AgentRun] = []

    def record(self, run: AgentRun) -> None:
        self.runs.append(run)


async def collect(
    agent: Agent, question: str, history: list[Turn] | None = None, lang: str = "en"
) -> list[Event]:
    return [event async for event in agent.stream(question, history or [], lang)]


def steps(found: list[Event]) -> list[str]:
    return [e.data["name"] for e in found if e.kind == "step"]


def detail(found: list[Event], name: str) -> dict[str, Any]:
    return next(e.data["detail"] for e in found if e.kind == "step" and e.data["name"] == name)


class TestAgent:
    async def test_small_talk_skips_the_lookups_and_the_grounding(self) -> None:
        model = ScriptedModel([say("Hi! Ask me about Erick's work.")])
        found = await collect(Agent(model, FakeKnowledge()), "Oi")
        assert steps(found) == ["route", "model", "guard"]
        assert model.seen[0][1] == []  # no tools offered
        assert found[-1].data["text"] == "Hi! Ask me about Erick's work."

    async def test_prefetch_tools_grounding_and_citations(self) -> None:
        model = ScriptedModel(
            [
                call("search_portfolio", '{"query": "langfuse"}'),
                call("read_case", '{"slug": "rhye"}', "c2"),
                say("Erick traced agents with Langfuse [3] and integrated 150 sources [2]."),
            ]
        )
        knowledge, tracer = FakeKnowledge(), Recorder()
        agent = Agent(model, knowledge, tracer=tracer)
        history = [Turn("user", "Hi"), Turn("assistant", "Hello")]
        found = [
            e
            async for e in agent.stream(
                "What did Erick build?", history, "en", trace="a" * 32, tags=("eval",)
            )
        ]
        assert steps(found) == [
            "route",
            "retrieve",
            "model",
            "tool.search_portfolio",
            "model",
            "tool.read_case",
            "model",
            "guard",
            "grounding",
        ]
        retrieve = detail(found, "retrieve")
        assert [f["n"] for f in retrieve["found"]] == [1, 2, 3]  # the profile comes first
        assert retrieve["steps"] == [
            {"name": "bm25.encode", "ms": 1.0},
            {"name": "dense.encode", "ms": 90.0},
        ]
        assert retrieve["dense"] == [{"title": "Vizzion", "heading": "Integrations", "score": 0.8}]
        assert detail(found, "grounding")["passed"] is True
        answer = found[-1].data
        assert [c["n"] for c in answer["citations"]] == [3, 2]
        assert answer["stop"] == "answered"
        assert knowledge.queries == ["What did Erick build?", "langfuse"]
        first_call = model.seen[0][0]
        assert [m.role for m in first_call] == ["system", "user", "assistant", "user", "system"]
        assert "Passages for this question" in first_call[-1].content
        assert model.seen[0][1] == ["search_portfolio", "read_case"]
        [run] = tracer.runs
        assert run.answer.startswith("Erick traced")
        assert (run.trace_id, list(run.tags)) == ("a" * 32, ["eval"])
        assert [g.name for g in run.generations] == ["model", "model", "model", "grounding"]
        assert run.prompts[0].startswith("system@")

    async def test_without_a_profile_the_search_alone_is_numbered(self) -> None:
        model = ScriptedModel([say("It integrated 150 sources [1].")])
        found = await collect(Agent(model, FakeKnowledge(profile_passage=None)), "Sources?")
        assert [f["n"] for f in detail(found, "retrieve")["found"]] == [1, 2]

        class Broken(FakeKnowledge):
            async def profile(self, lang: str) -> Passage | None:
                raise RuntimeError("database down")

        model = ScriptedModel([say("It integrated 150 sources [1].")])
        found = await collect(Agent(model, Broken()), "Sources?")
        assert [f["n"] for f in detail(found, "retrieve")["found"]] == [1, 2]
        assert found[-1].kind == "answer"

    async def test_tool_errors_are_reported_to_the_model(self) -> None:
        model = ScriptedModel(
            [
                call("search_portfolio", "{not json"),
                call("read_case", '{"slug": "ghost"}', "c2"),
                call("weather", "{}", "c3"),
                say("The site does not cover that."),
            ]
        )
        found = await collect(Agent(model, FakeKnowledge()), "Tell me about ghost")
        details = [
            e.data["detail"]
            for e in found
            if e.kind == "step" and e.data["name"].startswith("tool.")
        ]
        assert details == [
            {"error": "invalid arguments"},
            {"slug": "ghost", "found": []},
            {"error": "unknown tool"},
        ]
        tool_messages = [m.content for m in model.seen[-1][0] if m.role == "tool"]
        assert tool_messages[1] == "No case study called 'ghost'."

    async def test_slow_tools_time_out(self) -> None:
        class Slow(FakeKnowledge):
            async def search(self, query: str, lang: str, limit: int) -> Lookup:
                if query == "x":
                    await asyncio.sleep(0.1)
                return Lookup([])

        model = ScriptedModel([call("search_portfolio", '{"query": "x"}'), say("Done.")])
        agent = Agent(model, Slow(), budget=Budget(tool_timeout_seconds=0.01))
        found = await collect(agent, "q")
        assert detail(found, "tool.search_portfolio") == {"error": "timeout"}

    async def test_budget_ends_with_a_synthesis_without_tools(self) -> None:
        two_calls = call("search_portfolio", '{"query": "a"}')
        two_calls = type(two_calls)(
            "",
            (*two_calls.calls, *call("search_portfolio", '{"query": "b"}', "c2").calls),
            two_calls.usage,
            two_calls.model,
        )
        model = ScriptedModel([two_calls, say("What I found [1].")])
        agent = Agent(model, FakeKnowledge(), budget=Budget(max_tool_calls=1))
        found = await collect(agent, "dig deep")
        assert found[-1].data["stop"] == "tool_calls"
        last_messages, last_tools, _ = model.seen[-1]
        assert last_tools == []
        assert "no more lookups" in last_messages[-1].content
        details = [
            e.data["detail"]
            for e in found
            if e.kind == "step" and e.data["name"] == "tool.search_portfolio"
        ]
        assert details[1] == {"skipped": True}

    async def test_a_failed_check_is_rewritten_by_the_strong_model(self) -> None:
        model = ScriptedModel(
            [say("Erick integrated 300 sources."), say("It integrated 150 sources [2].")]
        )
        found = await collect(Agent(model, FakeKnowledge()), "How many sources?")
        assert steps(found)[-5:] == ["model", "guard", "rewrite", "guard", "grounding"]
        assert model.seen[-1][2] == "strong"
        assert "numbers not in the passages: 300" in model.seen[-1][0][-1].content
        assert found[-1].data["text"] == "It integrated 150 sources [2]."

    async def test_an_unsupported_claim_goes_to_the_rewrite_with_the_claim(self) -> None:
        model = ScriptedModel(
            [say("He integrated 150 sources [2] and won an award."), say("150 sources [2].")],
            verdicts=[say('{"unsupported": ["won an award", "see the contact form"]}')],
        )
        found = await collect(Agent(model, FakeKnowledge()), "How many sources?")
        grounding = detail(found, "grounding")
        # The meta remark is dropped; the invented fact goes back to the model.
        assert (grounding["passed"], grounding["unsupported"]) == (False, ["won an award"])
        assert "won an award" in model.seen[-1][0][-1].content
        assert found[-1].data["text"] == "150 sources [2]."

    async def test_still_flagged_after_the_rewrite_is_trimmed(self) -> None:
        model = ScriptedModel(
            [
                say("Erick integrated 150 sources [2]. He won a national award."),
                say(
                    "Erick integrated 150 sources at Vizzion, as the case shows [2]. "
                    "He won a national award."
                ),
            ],
            verdicts=[say('{"unsupported": ["won a national award"]}')] * 2,
        )
        found = await collect(Agent(model, FakeKnowledge()), "Sources?")
        assert steps(found)[-1] == "trim"
        assert (
            found[-1].data["text"]
            == "Erick integrated 150 sources at Vizzion, as the case shows [2]."
        )
        assert detail(found, "trim")["kept"] == len(found[-1].data["text"])

    async def test_nothing_left_after_trimming_points_to_erick(self) -> None:
        model = ScriptedModel([say("300 sources."), say("Still 300 sources.")])
        found = await collect(Agent(model, FakeKnowledge()), "How many sources?", lang="pt")
        assert steps(found)[-1] == "trim"
        assert found[-1].data["text"] == prompts.FALLBACK["pt"]
        found = await collect(
            Agent(ScriptedModel([say("300."), say("300.")]), FakeKnowledge()), "?", lang="it"
        )
        assert found[-1].data["text"] == prompts.FALLBACK["en"]

    async def test_an_unreadable_verdict_does_not_block_the_answer(self) -> None:
        model = ScriptedModel([say("150 sources [2].")], verdicts=[say("I think it is fine")])
        found = await collect(Agent(model, FakeKnowledge()), "Sources?")
        assert detail(found, "grounding") == {
            "model": "fake/model",
            "passages": [1, 2, 3],
            "passed": True,
            "unreadable": True,
        }
        assert found[-1].data["text"] == "150 sources [2]."

    async def test_a_model_failure_becomes_an_error_event(self) -> None:
        found = await collect(Agent(ScriptedModel(fail=True), FakeKnowledge()), "q")
        assert found[-1] == Event("error", {"message": "the assistant failed"})

    async def test_stops_cleanly_when_the_reader_leaves(self) -> None:
        agent = Agent(ScriptedModel([say("Hi.")]), FakeKnowledge(delay=0.05))
        stream = agent.stream("question", [], "en")
        first = await anext(stream)
        assert first.data["name"] == "route"
        await stream.aclose()


class TestSiteKnowledge:
    async def test_reads_search_cases_and_the_profile(self) -> None:
        world = make_world()
        await seed(world)
        search = world.search()
        await search.reindex()
        knowledge = SiteKnowledge(search.search, world.container().catalog)
        lookup = await knowledge.search("Loopia", "en", 3)
        assert lookup.passages[0].slug == "loopia"
        assert next(name for name, _ in lookup.steps) == "bm25.encode"
        assert lookup.dense
        assert (await knowledge.search("   ", "en", 3)).passages == []
        case = await knowledge.case("vizzion", "en")
        assert case is not None
        assert case.score == 1.0
        assert await knowledge.case("ghost", "en") is None
        assert await knowledge.case("vizzion", "xx") is None
        profile = await knowledge.profile("en")
        assert profile is not None
        assert profile.kind == "profile"
        assert await knowledge.profile("en") is profile  # cached
        assert await knowledge.profile("xx") is None
        empty = SiteKnowledge(search.search, make_world().container().catalog)
        assert await empty.profile("en") is None

    async def test_the_profile_card_and_its_cache(self) -> None:
        now = [0.0]

        def entry(title: str, **details: str) -> Any:
            return type("Entry", (), {"title": title, "summary": "One. Two.", "details": details})

        class Catalog:
            reads = 0

            async def profile(self, lang: Lang) -> Any:
                Catalog.reads += 1
                fields = {"name": "E", "headline": "Eng", "summary": "S", "location": None}
                return type("Profile", (), fields)

            async def entries(self, kind: Kind, lang: Lang) -> list[Any]:
                if kind is Kind.EXPERIENCE:
                    return [
                        entry("CTO", organization="Vizzion", start="2024-03", end="2025-10"),
                        entry("Engineer", organization="Loopia", start="2026-05"),
                        entry("Volunteer", organization="Club"),
                    ]
                return [entry("Rhye", state="active"), entry("Old", state="archived")]

        knowledge = SiteKnowledge(
            object(),  # type: ignore[arg-type]
            Catalog(),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )
        passage = await knowledge.profile("pt")
        assert passage is not None
        assert passage.text.splitlines() == [
            "E: Eng",
            "S",
            "Carreira: CTO, Vizzion (2024-03 até 2025-10)",
            "Carreira: Engineer, Loopia (2026-05 até hoje)",
            "Carreira: Volunteer, Club (hoje)",
            "Construindo agora: Rhye, One.",
        ]
        assert await knowledge.profile("pt") is passage  # cached
        now[0] = PROFILE_TTL_SECONDS + 1
        await knowledge.profile("pt")
        assert Catalog.reads == 2
        assert await knowledge.profile("xx") is None


@pytest.fixture
async def client(world: World) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(world.app()), base_url="https://a.t") as c:
        yield c


@pytest.fixture
def world() -> World:
    return make_world()


def parse(body: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in body.strip().split("\n\n"):
        kind, data = block.split("\n", 1)
        out.append((kind.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


class TestHttp:
    async def test_streams_steps_then_the_answer(self, client: AsyncClient, world: World) -> None:
        world.model.replies = [say("Hello there.", cost=0.25)]
        response = await client.post(
            "/api/chat", json={"message": "hi", "history": [{"role": "user", "content": "x"}]}
        )
        assert response.headers["content-type"].startswith("text/event-stream")
        found = parse(response.text)
        assert [kind for kind, _ in found] == ["step", "step", "step", "answer"]
        assert found[-1][1]["text"] == "Hello there."

    async def test_limits(self, client: AsyncClient, world: World) -> None:
        assert (await client.post("/api/chat", json={"message": ""})).status_code == 422
        world.limiter.hits[("chat-minute", "127.0.0.1")] = 999
        assert (await client.post("/api/chat", json={"message": "hi"})).status_code == 429
        world.limiter.hits.clear()
        app = client._transport.app  # type: ignore[attr-defined]
        app.state.assistant.spend.add(10)
        assert (await client.post("/api/chat", json={"message": "hi"})).status_code == 503

    async def test_an_unexpected_failure_still_ends_the_stream(self, client: AsyncClient) -> None:
        class Broken:
            async def stream(self, *args: object) -> AsyncIterator[Event]:
                raise RuntimeError("boom")
                yield  # pragma: no cover

        app = client._transport.app  # type: ignore[attr-defined]
        app.state.assistant = type(app.state.assistant)(
            Broken(),
            app.state.assistant.limiter,
            DailySpend(1),
        )
        found = parse((await client.post("/api/chat", json={"message": "hi"})).text)
        assert found == [("error", {"message": "the assistant failed"})]

    def test_daily_spend_resets_each_day(self) -> None:
        spend = DailySpend(1.0)
        spend.add(1.0)
        assert not spend.allows()
        spend._day = datetime(2020, 1, 1, tzinfo=UTC).date()
        assert spend.allows()


class TestOpenRouter:
    def chat(self, handler: Any) -> OpenRouterChat:
        http = httpx.AsyncClient(base_url="https://or.test", transport=httpx.MockTransport(handler))
        return OpenRouterChat(http, {"fast": ["a/fast", "b/backup"], "strong": ["c/strong"]})

    async def test_sends_tools_and_reads_tool_calls(self) -> None:
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "model": "a/fast",
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "search_portfolio",
                                            "arguments": '{"query":"x"}',
                                        }
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0001},
                },
            )

        chat = self.chat(handler)
        spec = ToolSpec("search_portfolio", "d", {"type": "object"})
        history = [
            Message("user", "q"),
            Message("assistant", "", (call("search_portfolio", "{}").calls[0],)),
            Message("tool", "result", tool_call_id="c1"),
        ]
        reply = await chat.complete(history, [spec], "fast")
        assert reply.calls[0].name == "search_portfolio"
        assert reply.calls[0].id == "call_0"
        assert reply.usage == Usage(10, 2, 0.0001)
        body = sent[0]
        assert body["models"] == ["a/fast", "b/backup"]
        assert body["model"] == "a/fast"
        assert body["tools"][0]["function"]["name"] == "search_portfolio"
        assert body["messages"][1]["tool_calls"][0]["function"]["name"] == "search_portfolio"
        assert body["messages"][1]["content"] is None
        assert body["messages"][2]["tool_call_id"] == "c1"
        await chat.close()

    async def test_plain_answers_and_bad_payloads(self) -> None:
        chat = self.chat(
            lambda _r: httpx.Response(200, json={"choices": [{"message": {"content": " Hi "}}]})
        )
        reply = await chat.complete([Message("user", "q")], [], "strong")
        assert (reply.text, reply.model, reply.usage) == ("Hi", "c/strong", Usage())
        broken = self.chat(lambda _r: httpx.Response(200, json={"error": "x"}))
        with pytest.raises(ChatError):
            await broken.complete([Message("user", "q")], [], "fast")
        assert OpenRouterChat.create("k", {"fast": ["m"], "strong": ["m"]})._models["fast"] == ["m"]

    def test_arguments(self) -> None:
        assert arguments('{"a": 1}') == {"a": 1}
        assert arguments("[1]") == {"raw": "[1]"}
        assert arguments("nope") == {"raw": "nope"}


START = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)


def _run(**changes: Any) -> AgentRun:
    values: dict[str, Any] = {
        "question": "q",
        "lang": "pt",
        "started_at": START,
        "steps": [
            StepRecord("route", 0, 1.5, {"mode": "tools"}),
            StepRecord("retrieve", 1.5, 300, {"found": []}),
            StepRecord("model", 301.5, 900, {"model": "a/fast"}),
            StepRecord("tool.read_case", 1201.5, 5, {"error": "timeout"}),
            StepRecord("guard", 1206.5, 1, {"passed": False}),
        ],
        "generations": [
            Generation(
                "model",
                "a/fast",
                302,
                899,
                [Message("assistant", "", call("x", "{}").calls)],
                "out",
                Usage(10, 2, 0.01),
            ),
            # A call no step contains is not attached to any.
            Generation("model", "a/fast", 5000, 1, [], "late", Usage()),
        ],
        "answer": "answer",
        "stop": "answered",
        "prompts": ["system@abc"],
        "trace_id": "f" * 32,
        "tags": ["eval"],
    }
    return AgentRun(**{**values, **changes})


class TestTracing:
    def test_a_run_becomes_an_agent_span_with_typed_children(self) -> None:
        root, route_, retrieve, model, tool, check = spans(_run())
        assert {s.trace_id for s in (root, route_, model)} == {"f" * 32}
        assert {route_.parent_id, model.parent_id} == {root.span_id}
        assert root.parent_id is None
        a = root.attributes
        assert a["langfuse.trace.name"] == "assistant.answer"
        assert a["langfuse.trace.tags"] == ["assistant", "pt", "eval"]
        assert a["langfuse.trace.metadata.prompts"] == ["system@abc"]
        assert a["langfuse.observation.type"] == "agent"
        assert root.end == datetime(2026, 11, 3, 18, 0, 1, 207500, tzinfo=UTC)
        assert route_.attributes["langfuse.observation.type"] == "span"
        assert retrieve.attributes["langfuse.observation.type"] == "retriever"
        assert tool.attributes["langfuse.observation.type"] == "tool"
        assert tool.attributes["langfuse.observation.level"] == "WARNING"
        assert check.attributes["langfuse.observation.type"] == "guardrail"
        assert check.attributes["langfuse.observation.level"] == "WARNING"
        m = model.attributes
        assert m["langfuse.observation.type"] == "generation"
        assert m["langfuse.observation.model.name"] == "a/fast"
        assert m["langfuse.observation.usage_details"] == {"input": 10, "output": 2}
        assert m["langfuse.observation.cost_details"] == {"total": 0.01}
        assert m["langfuse.observation.input"] == [
            {"role": "assistant", "content": "", "tool_calls": ["x"]}
        ]
        assert m["langfuse.observation.metadata.detail"] == {"model": "a/fast"}

    def test_an_eval_answer_is_an_experiment_item_on_every_span(self) -> None:
        experiment = Experiment("exp", "run 1", "ds", "assistant-a", {"any": ["150"]})
        root, *children = spans(_run(experiment=experiment))
        assert root.span_id == "f" * 16  # derived from the trace, so scores can point at it
        for span in (root, *children):
            assert span.attributes["langfuse.experiment.id"] == "exp"
            assert span.attributes["langfuse.experiment.item.id"] == "assistant-a"
            assert span.attributes["langfuse.experiment.item.root_observation_id"] == root.span_id
            assert span.attributes["langfuse.experiment.dataset.id"] == "ds"
        assert root.attributes["langfuse.experiment.item.expected_output"] == {"any": ["150"]}
        assert "langfuse.experiment.item.expected_output" not in children[0].attributes
        assert "langfuse.experiment.id" not in spans(_run())[0].attributes

    def test_a_run_without_an_id_or_steps_still_traces(self) -> None:
        [root] = spans(_run(trace_id="", steps=[], generations=[]))
        assert len(root.trace_id) == 32
        assert root.end == START

    async def test_the_tracer_sends_through_langfuse(self) -> None:
        sent: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(200)

        http = httpx.AsyncClient(base_url="https://lf.test", transport=httpx.MockTransport(handler))
        langfuse = Langfuse(http)
        LangfuseAgentTracer(langfuse).record(_run())
        await langfuse.close()
        [request] = sent
        assert request.url.path == "/api/public/otel/v1/traces"
