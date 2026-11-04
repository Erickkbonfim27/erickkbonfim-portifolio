"""The agent's evals: a versioned dataset of questions, each answered by the real agent
and checked by code, on the answer and on the trajectory.

Checks are deterministic: terms the answer must or must not contain, citations, which
cases it read, whether it searched, and how it got there (first pass, no fallback,
grounded). Each case's run is a trace; with a recorder, the dataset, the run and every
score land in Langfuse, linked to that trace.
"""

import asyncio
import logging
import statistics
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from portfolio.contexts.assistant.application.agent import Agent
from portfolio.contexts.assistant.application.ports import Experiment

log = logging.getLogger(__name__)

_QUANTILE_MIN = 2  # quantiles need two values
SEARCH_STEPS = frozenset({"retrieve", "tool.search_portfolio"})
CHECK_STEPS = frozenset({"guard", "grounding"})
# What a refusal looks like; a recruiter question should never get one.
REFUSALS = (
    "nao ha informac",
    "nao encontrei",
    "nao fala disso",
    "nao tenho informac",
    "doesn't cover",
    "does not cover",
    "no information",
    "couldn't find",
)


def _plain(text: str) -> str:
    """Case- and accent-insensitive, so "integração" matches "integracao"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True, slots=True)
class Expected:
    any: tuple[str, ...] = ()  # at least one of these
    all: tuple[str, ...] = ()  # every one of these
    forbid: tuple[str, ...] = ()  # none of these
    cases: tuple[str, ...] = ()  # case studies it must cite or read
    search: bool | None = None  # None: not checked
    cite: bool = True  # recruiter questions only, unless the case says otherwise


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    kind: str  # recruiter | smalltalk | adversarial
    question: str
    lang: str
    expected: Expected

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> "EvalCase":
        kind = str(data.get("kind", "recruiter"))
        exp = data.get("expected", {})
        search = exp.get("search", {"recruiter": True, "smalltalk": False}.get(kind))
        return cls(
            id=str(data["id"]),
            kind=kind,
            question=str(data["input"]["question"]),
            lang=str(data["input"].get("lang", "pt")),
            expected=Expected(
                any=tuple(exp.get("any", ())),
                all=tuple(exp.get("all", ())),
                forbid=tuple(exp.get("forbid", ())),
                cases=tuple(exp.get("cases", ())),
                search=search,
                cite=bool(exp.get("cite", kind == "recruiter")),
            ),
        )

    def as_item(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Input and expected output, as the dataset item stores them."""
        e = self.expected
        expected: dict[str, Any] = {
            "any": list(e.any),
            "all": list(e.all),
            "forbid": list(e.forbid),
            "cases": list(e.cases),
            "search": e.search,
            "cite": e.cite,
        }
        return {"question": self.question, "lang": self.lang}, expected


@dataclass(frozen=True, slots=True)
class Outcome:
    case: EvalCase
    trace: str
    answer: str
    steps: tuple[str, ...]
    checks: dict[str, bool]
    latency_s: float
    cost_usd: float
    error: str | None = None
    notes: tuple[str, ...] = ()  # why the guard or the grounding check flagged it

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    @property
    def first_pass(self) -> bool:
        """No rewrite: the first draft held. Tracked, not required: a rewrite that fixes
        an overstatement ("more than 150") is the checks doing their job."""
        return "rewrite" not in self.steps

    @property
    def failed_checks(self) -> list[str]:
        return [name for name, ok in self.checks.items() if not ok]


def check(
    case: EvalCase, steps: Sequence[Mapping[str, Any]], answer: Mapping[str, Any] | None
) -> dict[str, bool]:
    """Every check that applies to this case, by name."""
    e = case.expected
    if answer is None:
        return {"answered": False}
    text = _plain(str(answer.get("text", "")))
    names = [str(s["name"]) for s in steps]
    verdicts = [s for s in steps if s["name"] in CHECK_STEPS]
    slugs = {str(c.get("slug") or "") for c in answer.get("citations", [])}
    slugs |= {str(s["detail"].get("slug", "")) for s in steps if s["name"] == "tool.read_case"}
    out = {
        "answered": bool(text.strip()),
        "no_trim": "trim" not in names,
        "grounded": bool(verdicts) and verdicts[-1]["detail"].get("passed") is True,
    }
    if case.kind == "smalltalk" or answer.get("stop") == "off_topic":
        out.pop("grounded")  # small talk and the site's off-topic reply: nothing to check
    if e.any:
        out["terms_any"] = any(_plain(term) in text for term in e.any)
    if e.all:
        out["terms_all"] = all(_plain(term) in text for term in e.all)
    if e.forbid:
        out["forbidden_absent"] = not any(_plain(term) in text for term in e.forbid)
    if e.cases:
        out["read_cases"] = all(any(slug in s for s in slugs) for slug in e.cases)
    if e.cite:
        out["cites"] = bool(answer.get("citations"))
    if e.search is not None:
        out["searched" if e.search else "no_search"] = e.search == bool(
            SEARCH_STEPS.intersection(names)
        )
    if case.kind == "recruiter":
        out["no_refusal"] = not any(r in text for r in REFUSALS)
    return out


class EvalRecorder(Protocol):
    """Where the dataset, the runs and the scores are kept (Langfuse)."""

    async def upsert_dataset(self, name: str, description: str, metadata: Mapping[str, Any]) -> str:
        """Returns the dataset's id."""
        ...

    async def upsert_item(
        self,
        dataset: str,
        item_id: str,
        input: Mapping[str, Any],
        expected: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None: ...

    async def link_run(
        self, dataset_run: str, item_id: str, trace: str, metadata: Mapping[str, Any]
    ) -> None: ...

    async def scores(self, scores: Sequence[tuple[str, str, float | bool, str | None]]) -> None:
        """(trace id, name, value, comment) each."""
        ...

    async def flush(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Report:
    run: str
    outcomes: list[Outcome]
    synced: bool

    @property
    def pass_rate(self) -> float:
        return sum(o.passed for o in self.outcomes) / len(self.outcomes) if self.outcomes else 0

    @property
    def leaks(self) -> list[Outcome]:
        """Answers that said something they must never say: these fail the gate alone."""
        return [o for o in self.outcomes if o.checks.get("forbidden_absent") is False]

    @property
    def first_pass_rate(self) -> float:
        return sum(o.first_pass for o in self.outcomes) / len(self.outcomes) if self.outcomes else 0

    def check_rates(self) -> dict[str, float]:
        totals: dict[str, list[bool]] = {}
        for outcome in self.outcomes:
            for name, ok in outcome.checks.items():
                totals.setdefault(name, []).append(ok)
        return {name: sum(oks) / len(oks) for name, oks in totals.items()}

    def latency(self, quantile: float) -> float:
        values = sorted(o.latency_s for o in self.outcomes)
        if len(values) < _QUANTILE_MIN:
            return values[0] if values else 0.0
        return statistics.quantiles(values, n=100, method="inclusive")[round(quantile * 100) - 1]

    @property
    def cost(self) -> float:
        return sum(o.cost_usd for o in self.outcomes)

    def gate(self, min_pass: float) -> bool:
        return self.pass_rate >= min_pass and not self.leaks


@dataclass(frozen=True, slots=True)
class RunEval:
    agent: Agent
    recorder: EvalRecorder | None = None
    concurrency: int = 3
    case_timeout_seconds: float = 90.0
    new_trace: Callable[[], str] = field(default=lambda: uuid4().hex)
    new_experiment: Callable[[], str] = field(default=lambda: str(uuid4()))

    async def __call__(
        self,
        dataset: str,
        cases: Sequence[EvalCase],
        run: str,
        metadata: Mapping[str, Any],
    ) -> Report:
        recorder = self.recorder
        dataset_id = await _sync(recorder, dataset, cases) if recorder is not None else None
        synced = dataset_id is not None
        experiment = self.new_experiment()
        gate = asyncio.Semaphore(self.concurrency)

        async def one(case: EvalCase) -> Outcome:
            # Each answer's trace is an item of this run's experiment in Langfuse.
            joined = (
                Experiment(experiment, run, dataset_id, _item_id(dataset, case), case.as_item()[1])
                if dataset_id is not None
                else None
            )
            async with gate:
                return await self._answer(case, joined)

        outcomes = list(await asyncio.gather(*(one(case) for case in cases)))
        if recorder is not None and synced:
            synced = await _record(recorder, dataset, run, metadata, outcomes)
        return Report(run, outcomes, synced)

    async def _answer(self, case: EvalCase, experiment: Experiment | None) -> Outcome:
        trace = self.new_trace()
        steps: list[dict[str, Any]] = []
        answer: dict[str, Any] | None = None
        error: str | None = None
        try:
            async with asyncio.timeout(self.case_timeout_seconds):
                async for event in self.agent.stream(
                    case.question,
                    (),
                    case.lang,
                    trace=trace,
                    tags=("eval", case.kind),
                    experiment=experiment,
                ):
                    if event.kind == "step":
                        steps.append(event.data)
                    elif event.kind == "answer":
                        answer = event.data
                    else:
                        error = str(event.data.get("message", "error"))
        except Exception as exc:  # one broken or stuck case must not stop the run
            log.exception("eval: %s failed", case.id)
            error = repr(exc)
        usage = (answer or {}).get("usage", {})
        return Outcome(
            case=case,
            trace=trace,
            answer=str((answer or {}).get("text", "")),
            steps=tuple(str(s["name"]) for s in steps),
            checks=check(case, steps, answer),
            latency_s=round(float(usage.get("ms", 0)) / 1000, 2),
            cost_usd=float(usage.get("cost", 0)),
            error=error,
            notes=tuple(
                f"{s['name']}: {reason}"
                for s in steps
                if s["name"] in CHECK_STEPS
                for reason in [*s["detail"].get("reasons", []), *s["detail"].get("unsupported", [])]
            ),
        )


async def _sync(recorder: EvalRecorder, dataset: str, cases: Sequence[EvalCase]) -> str | None:
    """The dataset's id once it and its items are in Langfuse; None when that failed."""
    try:
        dataset_id = await recorder.upsert_dataset(
            dataset,
            "Questions a recruiter or an engineer asks the site's agent, plus adversarial "
            "ones. Source of truth: backend/evals/ in the repository.",
            {"source": f"backend/evals/{dataset}.jsonl"},
        )
        for case in cases:
            given, expected = case.as_item()
            await recorder.upsert_item(
                dataset, _item_id(dataset, case), given, expected, {"kind": case.kind}
            )
    except Exception:
        log.warning("eval: dataset not synced to Langfuse", exc_info=True)
        return None
    return dataset_id


async def _record(
    recorder: EvalRecorder,
    dataset: str,
    run: str,
    metadata: Mapping[str, Any],
    outcomes: Sequence[Outcome],
) -> bool:
    try:
        await recorder.flush()  # the traces exist before anything points at them
        scores: list[tuple[str, str, float | bool, str | None]] = []
        for o in outcomes:
            await recorder.link_run(run, _item_id(dataset, o.case), o.trace, metadata)
            scores.append((o.trace, "passed", o.passed, ", ".join(o.failed_checks) or None))
            scores += [(o.trace, name, ok, None) for name, ok in o.checks.items()]
            scores.append((o.trace, "first_pass", o.first_pass, None))
            scores.append((o.trace, "latency_s", o.latency_s, None))
            scores.append((o.trace, "cost_usd", o.cost_usd, None))
        await recorder.scores(scores)
    except Exception:
        log.warning("eval: run not recorded in Langfuse", exc_info=True)
        return False
    return True


def _item_id(dataset: str, case: EvalCase) -> str:
    return f"{dataset}-{case.id}"
