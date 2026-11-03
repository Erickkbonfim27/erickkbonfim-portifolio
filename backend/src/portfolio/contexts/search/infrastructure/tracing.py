"""Search runs as Langfuse traces: a retriever span per search, a child per step."""

from datetime import timedelta

from portfolio.contexts.search.application.ports import SearchRun
from portfolio.platform.langfuse import Langfuse, Span, span_id, trace_id

# How Langfuse draws each step.
KINDS = {"bm25.encode": "embedding", "dense.encode": "embedding"}


class LangfuseSearchTracer:
    def __init__(self, langfuse: Langfuse) -> None:
        self._langfuse = langfuse

    def record(self, run: SearchRun) -> None:
        self._langfuse.send(spans(run))


def spans(run: SearchRun) -> list[Span]:
    """The spans of one run. Only the question goes out, never who asked."""
    trace = trace_id()
    root = span_id()
    query = {"query": run.query.text, "lang": run.query.lang, "limit": run.query.limit}
    hits = [
        {"title": h.title, "heading": h.heading, "kind": h.kind, "score": h.score} for h in run.hits
    ]
    end = run.started_at + timedelta(
        milliseconds=max((s.start_ms + s.ms for s in run.steps), default=0)
    )
    out = [
        Span(
            trace,
            root,
            run.name,
            run.started_at,
            end,
            {
                "langfuse.trace.name": run.name,
                "langfuse.trace.input": query,
                "langfuse.trace.output": {"hits": hits},
                "langfuse.trace.tags": ["search", run.query.lang],
                "langfuse.trace.metadata.degraded": run.degraded,
                "langfuse.observation.type": "retriever",
                "langfuse.observation.input": query,
                "langfuse.observation.output": {"hits": hits},
                **({"langfuse.observation.level": "WARNING"} if run.degraded else {}),
            },
        )
    ]
    for step in run.steps:
        begin = run.started_at + timedelta(milliseconds=step.start_ms)
        out.append(
            Span(
                trace,
                span_id(),
                step.name,
                begin,
                begin + timedelta(milliseconds=step.ms),
                {"langfuse.observation.type": KINDS.get(step.name, "span")},
                root,
            )
        )
    return out
