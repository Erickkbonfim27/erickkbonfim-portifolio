"""Agent runs as Langfuse traces: an agent span per answer, a child per node. A node that
called the model is a generation (model, messages, tokens, cost); tools, retrieval and
the checks are typed as such, so Langfuse draws the graph the site shows."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from portfolio.contexts.assistant.application.ports import (
    AgentRun,
    Experiment,
    Generation,
    Message,
    StepRecord,
)
from portfolio.platform.langfuse import Langfuse, Span, root_span_id, span_id, trace_id

KINDS = {"retrieve": "retriever", "guard": "guardrail", "grounding": "guardrail"}


def _messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    return [
        {
            "role": m.role,
            "content": m.content,
            **({"tool_calls": [c.name for c in m.calls]} if m.calls else {}),
        }
        for m in messages
    ]


def _generation(step: StepRecord, generations: Sequence[Generation]) -> Generation | None:
    """The model call a step made: same name, started within the step."""
    for generation in generations:
        if generation.name == step.name and (
            step.start_ms <= generation.start_ms <= step.start_ms + step.ms
        ):
            return generation
    return None


class LangfuseAgentTracer:
    def __init__(self, langfuse: Langfuse) -> None:
        self._langfuse = langfuse

    def record(self, run: AgentRun) -> None:
        self._langfuse.send(spans(run))


def _experiment(experiment: Experiment | None, root: str) -> dict[str, Any]:
    """What makes a trace an experiment item in Langfuse v4: the same keys on every span."""
    if experiment is None:
        return {}
    return {
        "langfuse.experiment.id": experiment.id,
        "langfuse.experiment.name": experiment.name,
        "langfuse.experiment.dataset.id": experiment.dataset_id,
        "langfuse.experiment.item.id": experiment.item_id,
        "langfuse.experiment.item.root_observation_id": root,
    }


def spans(run: AgentRun) -> list[Span]:
    """Only the question and the answer go out, never who asked."""
    trace = run.trace_id or trace_id()
    root = root_span_id(trace)
    shared = _experiment(run.experiment, root)
    total = max((s.start_ms + s.ms for s in run.steps), default=0)
    question = {"question": run.question, "lang": run.lang}
    out = [
        Span(
            trace,
            root,
            "assistant.answer",
            run.started_at,
            run.started_at + timedelta(milliseconds=total),
            {
                "langfuse.trace.name": "assistant.answer",
                "langfuse.trace.input": question,
                "langfuse.trace.output": {"answer": run.answer},
                "langfuse.trace.tags": ["assistant", run.lang, *run.tags],
                "langfuse.trace.metadata.stop": run.stop,
                "langfuse.trace.metadata.prompts": list(run.prompts),
                "langfuse.observation.type": "agent",
                "langfuse.observation.input": question,
                "langfuse.observation.output": {"answer": run.answer, "stop": run.stop},
                **shared,
                **(
                    {"langfuse.experiment.item.expected_output": dict(run.experiment.expected)}
                    if run.experiment
                    else {}
                ),
            },
        )
    ]
    for step in run.steps:
        begin = run.started_at + timedelta(milliseconds=step.start_ms)
        failed = step.detail.get("passed") is False or "error" in step.detail
        attributes: dict[str, Any] = {
            "langfuse.observation.type": (
                "tool" if step.name.startswith("tool.") else KINDS.get(step.name, "span")
            ),
            "langfuse.observation.output": dict(step.detail),
            **({"langfuse.observation.level": "WARNING"} if failed else {}),
            **shared,
        }
        generation = _generation(step, run.generations)
        if generation is not None:
            attributes.update(
                {
                    "langfuse.observation.type": "generation",
                    "langfuse.observation.model.name": generation.model,
                    "langfuse.observation.input": _messages(generation.messages),
                    "langfuse.observation.output": generation.output,
                    "langfuse.observation.metadata.detail": dict(step.detail),
                    "langfuse.observation.usage_details": {
                        "input": generation.usage.input_tokens,
                        "output": generation.usage.output_tokens,
                    },
                    "langfuse.observation.cost_details": {"total": generation.usage.cost},
                }
            )
        out.append(
            Span(
                trace,
                span_id(),
                step.name,
                begin,
                begin + timedelta(milliseconds=step.ms),
                attributes,
                root,
            )
        )
    return out
