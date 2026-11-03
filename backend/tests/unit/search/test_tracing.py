import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from portfolio.contexts.search.application.ports import SearchRun, Step
from portfolio.contexts.search.domain.model import SearchHit, SearchQuery
from portfolio.contexts.search.infrastructure.tracing import LangfuseSearchTracer, spans
from portfolio.platform import langfuse as lf
from portfolio.platform.langfuse import Langfuse, LangfuseError, Span, otlp

START = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
RUN = SearchRun(
    name="search.explain",
    query=SearchQuery.build("RAG em produção", "pt", 3),
    started_at=START,
    steps=[Step("bm25.encode", 0, 2.5), Step("dense.encode", 2.5, 900)],
    hits=[SearchHit(uuid4(), "project", "rhye", "Rhye", "Aeva", "…", 0.5)],
    degraded=False,
)


def test_a_run_becomes_a_retriever_span_with_a_child_per_step() -> None:
    root, bm25, dense = spans(RUN)
    a = root.attributes
    assert a["langfuse.trace.name"] == "search.explain"
    assert a["langfuse.trace.input"] == {"query": "RAG em produção", "lang": "pt", "limit": 3}
    assert a["langfuse.trace.output"]["hits"] == [
        {"title": "Rhye", "heading": "Aeva", "kind": "project", "score": 0.5}
    ]
    assert a["langfuse.observation.type"] == "retriever"
    assert "langfuse.observation.level" not in a
    assert root.end == datetime(2026, 11, 3, 18, 0, 0, 902500, tzinfo=UTC)
    assert bm25.parent_id == dense.parent_id == root.span_id
    assert bm25.trace_id == dense.trace_id == root.trace_id
    assert dense.attributes == {"langfuse.observation.type": "embedding"}
    assert dense.start == datetime(2026, 11, 3, 18, 0, 0, 2500, tzinfo=UTC)


def test_a_degraded_run_is_a_warning() -> None:
    degraded = SearchRun(RUN.name, RUN.query, START, [Step("rrf.fuse", 0, 1)], [], True)
    root, fuse = spans(degraded)
    assert root.attributes["langfuse.observation.level"] == "WARNING"
    assert fuse.attributes == {"langfuse.observation.type": "span"}


def test_otlp_encodes_each_attribute_type() -> None:
    span = Span(
        "a" * 32,
        "b" * 16,
        "s",
        START,
        START,
        {"s": "x", "b": True, "i": 3, "f": 0.5, "l": ["x", "y"], "d": {"k": 1}, "n": None},
        "c" * 16,
    )
    [resource] = otlp([span], "svc")["resourceSpans"]
    [encoded] = resource["scopeSpans"][0]["spans"]
    assert encoded["parentSpanId"] == "c" * 16
    assert encoded["startTimeUnixNano"] == str(int(START.timestamp()) * 10**9)
    values = {a["key"]: a["value"] for a in encoded["attributes"]}
    assert values == {
        "s": {"stringValue": "x"},
        "b": {"boolValue": True},
        "i": {"intValue": "3"},
        "f": {"doubleValue": 0.5},
        "l": {"arrayValue": {"values": [{"stringValue": "x"}, {"stringValue": "y"}]}},
        "d": {"stringValue": '{"k": 1}'},
    }
    root = otlp([Span("a" * 32, "b" * 16, "s", START, START)], "svc")
    assert "parentSpanId" not in root["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert len(lf.trace_id()) == 32
    assert len(lf.span_id()) == 16


def _langfuse(handler: Any, environment: str = "production") -> Langfuse:
    http = httpx.AsyncClient(base_url="https://lf.test", transport=httpx.MockTransport(handler))
    return Langfuse(http, environment)


async def test_sends_in_the_background_and_waits_on_close() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/public/otel/v1/traces"
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={})

    langfuse = _langfuse(handler, "eval")
    assert langfuse.environment == "eval"
    LangfuseSearchTracer(langfuse).record(RUN)
    assert sent == []  # queued, not awaited by the caller
    await langfuse.close()
    found = sent[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(found) == 3
    environments = {
        a["value"]["stringValue"]
        for s in found
        for a in s["attributes"]
        if a["key"] == "langfuse.environment"
    }
    assert environments == {"eval"}


async def test_a_failing_langfuse_never_breaks_the_caller(caplog: pytest.LogCaptureFixture) -> None:
    langfuse = _langfuse(lambda _request: httpx.Response(401))
    langfuse.send(spans(RUN))
    await asyncio.sleep(0.01)
    await langfuse.close()
    assert "trace not sent" in caplog.text


async def test_close_without_traces_and_the_factory() -> None:
    langfuse = Langfuse.create("https://cloud.langfuse.com/", "pk", "sk", "development")
    assert str(langfuse._http.base_url) == "https://cloud.langfuse.com"
    assert langfuse.environment == "development"
    await langfuse.close()


class TestApi:
    async def test_datasets_items_runs_and_scores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.url.path, json.loads(request.content)))
            return httpx.Response(207 if "ingestion" in request.url.path else 200, json={})

        monkeypatch.setattr(lf, "BATCH", 2)
        langfuse = _langfuse(handler, "eval")
        assert await langfuse.upsert_dataset("assistant", "d", {"source": "x"}) == ""
        await langfuse.upsert_item("assistant", "assistant-a", {"q": 1}, {"any": []}, {"k": 1})
        await langfuse.link_run("run", "assistant-a", "t" * 32, {"m": 1})
        await langfuse.scores(
            [("t", "passed", True, "why"), ("t", "latency_s", 1.5, None), ("t", "x", False, None)]
        )
        await langfuse.flush()
        paths = [path for path, _ in calls]
        assert paths == [
            "/api/public/v2/datasets",
            "/api/public/dataset-items",
            "/api/public/dataset-run-items",
            "/api/public/ingestion",
            "/api/public/ingestion",
        ]
        assert calls[1][1]["expectedOutput"] == {"any": []}
        assert calls[2][1]["traceId"] == "t" * 32
        first, second = calls[3][1]["batch"], calls[4][1]["batch"]
        assert [e["type"] for e in first] == ["score-create", "score-create"]
        assert first[0]["body"] | {"id": None} == {
            "id": None,
            "traceId": "t",
            "observationId": "t",
            "name": "passed",
            "value": 1.0,
            "dataType": "BOOLEAN",
            "environment": "eval",
            "comment": "why",
        }
        assert first[1]["body"]["dataType"] == "NUMERIC"
        assert len(second) == 1

    async def test_rejected_scores_raise(self) -> None:
        langfuse = _langfuse(lambda _r: httpx.Response(207, json={"errors": [{"status": 400}]}))
        with pytest.raises(LangfuseError):
            await langfuse.scores([("t", "passed", True, None)])

    async def test_retries_a_moment_of_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def instant(_seconds: float) -> None:
            return None

        monkeypatch.setattr("portfolio.platform.langfuse.asyncio.sleep", instant)
        answers: list[httpx.Response | Exception] = [
            httpx.ConnectError("down"),
            httpx.Response(503),
            httpx.Response(200, json={}),
        ]

        def handler(_request: httpx.Request) -> httpx.Response:
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        await _langfuse(handler).upsert_dataset("d", "", {})
        assert answers == []

        def down(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        with pytest.raises(httpx.ConnectError):
            await _langfuse(down).upsert_dataset("d", "", {})
        with pytest.raises(httpx.HTTPStatusError):
            await _langfuse(lambda _r: httpx.Response(429)).upsert_dataset("d", "", {})
