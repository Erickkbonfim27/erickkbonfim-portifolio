import asyncio
import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from portfolio import cli
from portfolio.contexts.assistant.application.agent import Agent, Event
from portfolio.contexts.assistant.application.evals import (
    EvalCase,
    Outcome,
    Report,
    RunEval,
    check,
)
from portfolio.contexts.assistant.application.ports import AgentRun
from portfolio.contexts.assistant.interfaces import cli as eval_cli
from tests.unit.assistant.fakes import FakeKnowledge, ScriptedModel, say
from tests.unit.support import REQUIRED_SETTINGS, make_world

DATASET = Path(__file__).parents[3] / "evals" / "assistant.jsonl"


def case(**fields: Any) -> EvalCase:
    data: dict[str, Any] = {"id": "c", "input": {"question": "Q?"}, **fields}
    return EvalCase.parse(data)


def step(name: str, **detail: Any) -> dict[str, Any]:
    return {"name": name, "ms": 1.0, "detail": detail}


ANSWER = {
    "text": "Erick integrou 150 integrações na Vizzion [1].",
    "citations": [{"n": 1, "slug": "vizzion"}],
}
GOOD_PATH = [step("route"), step("retrieve"), step("model"), step("guard", passed=True)]
GOOD_PATH.append(step("grounding", passed=True))


class TestCheck:
    def test_parses_defaults_by_kind(self) -> None:
        recruiter = case()
        assert (recruiter.kind, recruiter.lang, recruiter.expected.search) == (
            "recruiter",
            "pt",
            True,
        )
        assert case(kind="smalltalk").expected.search is False
        assert case(kind="adversarial").expected.search is None
        given, expected = case(expected={"any": ["a"], "cite": False}).as_item()
        assert given == {"question": "Q?", "lang": "pt"}
        assert expected["any"] == ["a"]
        assert expected["cite"] is False

    def test_a_good_answer_passes_every_check(self) -> None:
        checks = check(
            case(expected={"any": ["integracoes"], "all": ["Vizzion"], "cases": ["vizzion"]}),
            GOOD_PATH,
            ANSWER,
        )
        assert checks == {
            "answered": True,
            "no_trim": True,
            "grounded": True,
            "terms_any": True,
            "terms_all": True,
            "read_cases": True,
            "cites": True,
            "searched": True,
            "no_refusal": True,
        }

    def test_each_failure_is_named(self) -> None:
        refusal = {"text": "O site não fala disso.", "citations": []}
        path = [step("route"), step("model"), step("guard", passed=False), step("trim")]
        checks = check(
            case(expected={"any": ["x"], "forbid": ["site"], "cases": ["rhye"]}), path, refusal
        )
        assert {name for name, ok in checks.items() if not ok} == {
            "no_trim",
            "grounded",
            "terms_any",
            "forbidden_absent",
            "read_cases",
            "cites",
            "searched",
            "no_refusal",
        }

    def test_small_talk_and_read_cases(self) -> None:
        hi = check(
            case(kind="smalltalk", expected={"cite": False}), [step("model")], {"text": "Oi!"}
        )
        assert hi == {"answered": True, "no_trim": True, "no_search": True}
        read = [step("tool.read_case", slug="rhye"), step("grounding", passed=True)]
        assert check(case(expected={"cases": ["rhye"]}), read, {"text": "x"})["read_cases"]

    def test_an_adversarial_case_checks_only_what_it_says(self) -> None:
        checks = check(case(kind="adversarial", expected={"forbid": ["Paris"]}), [], ANSWER)
        assert set(checks) == {"answered", "no_trim", "grounded", "forbidden_absent"}

    def test_no_answer_fails_alone(self) -> None:
        assert check(case(), [], None) == {"answered": False}


def outcome(id_: str, checks: dict[str, bool], latency: float = 1.0, **rest: Any) -> Outcome:
    return Outcome(case(id=id_), "t", "a", rest.pop("steps", ()), checks, latency, 0.001, **rest)


class TestReport:
    def test_rates_latency_cost_and_the_gate(self) -> None:
        report = Report(
            "run",
            [
                outcome("a", {"answered": True}, 1.0),
                outcome("b", {"answered": True}, 3.0, steps=("model", "rewrite")),
                outcome("c", {"answered": False}, 5.0),
            ],
            synced=True,
        )
        assert report.pass_rate == pytest.approx(2 / 3)
        assert report.first_pass_rate == pytest.approx(2 / 3)
        assert report.check_rates() == {"answered": pytest.approx(2 / 3)}
        assert report.latency(0.5) == 3.0
        assert report.cost == pytest.approx(0.003)
        assert report.gate(0.6)
        assert not report.gate(0.9)

    def test_a_leak_fails_the_gate_alone(self) -> None:
        report = Report("r", [outcome("a", {"forbidden_absent": False})] * 1, synced=False)
        assert report.leaks
        assert not report.gate(0.0)

    def test_empty_and_single(self) -> None:
        assert Report("r", [], synced=False).pass_rate == 0
        assert Report("r", [], synced=False).first_pass_rate == 0
        assert Report("r", [], synced=False).latency(0.95) == 0.0
        assert Report("r", [outcome("a", {}, 2.0)], synced=False).latency(0.95) == 2.0


class Tracer:
    def __init__(self) -> None:
        self.runs: list[AgentRun] = []

    def record(self, run: AgentRun) -> None:
        self.runs.append(run)


class FakeRecorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[tuple[str, Any]] = []

    def _log(self, name: str, value: Any) -> None:
        if name == self.fail_on:
            raise RuntimeError(name)
        self.calls.append((name, value))

    async def upsert_dataset(self, name: str, description: str, metadata: Mapping[str, Any]) -> str:
        self._log("dataset", name)
        return "ds-1"

    async def upsert_item(
        self,
        dataset: str,
        item_id: str,
        input: Mapping[str, Any],
        expected: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        self._log("item", item_id)

    async def link_run(
        self, dataset_run: str, item_id: str, trace: str, metadata: Mapping[str, Any]
    ) -> None:
        self._log("link", (dataset_run, item_id, trace))

    async def scores(self, scores: Sequence[tuple[str, str, float | bool, str | None]]) -> None:
        self._log("scores", list(scores))

    async def flush(self) -> None:
        self._log("flush", None)


def agent(*replies: str) -> Agent:
    return Agent(ScriptedModel([say(r) for r in replies]), FakeKnowledge())


CASES = [
    case(id="hi", kind="smalltalk", input={"question": "Oi", "lang": "pt"}),
    case(id="sources", expected={"any": ["150"]}),
]


class TestRunEval:
    async def test_runs_each_case_links_its_trace_and_scores_it(self) -> None:
        recorder = FakeRecorder()
        traces = iter(["t1", "t2"])
        tracer = Tracer()
        evaluate = RunEval(
            Agent(
                ScriptedModel([say("Olá!"), say("Erick integrou 150 fontes [2].")]),
                FakeKnowledge(),
                tracer=tracer,
            ),
            recorder,
            concurrency=1,
            new_trace=lambda: next(traces),
            new_experiment=lambda: "exp-1",
        )
        report = await evaluate("assistant", CASES, "run-1", {"models": {}})
        assert report.synced
        assert [o.passed for o in report.outcomes] == [True, True]
        assert report.outcomes[1].steps[-1] == "grounding"
        names = [name for name, _ in recorder.calls]
        assert names == ["dataset", "item", "item", "flush", "link", "link", "scores"]
        assert recorder.calls[4][1] == ("run-1", "assistant-hi", "t1")
        scores = recorder.calls[-1][1]
        assert ("t2", "passed", True, None) in scores
        assert ("t2", "first_pass", True, None) in scores
        assert {name for _, name, _, _ in scores} >= {"latency_s", "cost_usd", "searched"}
        # Each trace is an item of the run's experiment.
        experiments = [run.experiment for run in tracer.runs]
        assert [(e.id, e.name, e.dataset_id, e.item_id) for e in experiments if e] == [
            ("exp-1", "run-1", "ds-1", "assistant-hi"),
            ("exp-1", "run-1", "ds-1", "assistant-sources"),
        ]
        assert experiments[1] is not None
        assert experiments[1].expected["any"] == ["150"]

    async def test_without_a_recorder_it_still_reports(self) -> None:
        report = await RunEval(agent("Olá!"))("assistant", CASES[:1], "run", {})
        assert not report.synced
        assert report.outcomes[0].passed

    @pytest.mark.parametrize("fail_on", ["dataset", "scores"])
    async def test_langfuse_failures_never_stop_the_run(self, fail_on: str) -> None:
        report = await RunEval(agent("Olá!"), FakeRecorder(fail_on))("a", CASES[:1], "r", {})
        assert not report.synced
        assert report.outcomes[0].passed

    async def test_a_failed_or_stuck_case_is_a_failure_not_a_crash(self) -> None:
        broken = Agent(ScriptedModel(fail=True), FakeKnowledge())
        [failed] = (await RunEval(broken)("a", CASES[1:], "r", {})).outcomes
        assert (failed.error, failed.checks) == ("the assistant failed", {"answered": False})

        class Stuck:
            async def stream(self, *args: object, **kwargs: object) -> AsyncGenerator[Event]:
                await asyncio.sleep(1)
                yield Event("answer", {})  # pragma: no cover

        stuck = RunEval(Stuck(), case_timeout_seconds=0.01)  # type: ignore[arg-type]
        [timed_out] = (await stuck("a", CASES[1:], "r", {})).outcomes
        assert timed_out.error == "TimeoutError()"
        assert not timed_out.passed


class TestCli:
    def test_the_dataset_in_the_repo_parses(self) -> None:
        cases = eval_cli.load(DATASET)
        assert len(cases) >= 30
        assert len({c.id for c in cases}) == len(cases)
        assert {c.kind for c in cases} == {"recruiter", "smalltalk", "adversarial"}

    def test_load_skips_blanks_and_comments(self, tmp_path: Path) -> None:
        path = tmp_path / "set.jsonl"
        path.write_text('// note\n\n{"id": "a", "input": {"question": "Q"}}\n')
        assert [c.id for c in eval_cli.load(path)] == ["a"]

    def test_lines(self) -> None:
        report = Report(
            "run",
            [
                outcome("ok", {"answered": True}),
                outcome("fixed", {"answered": True}, steps=("rewrite",), notes=("guard: x",)),
                outcome("bad", {"answered": False}, error="boom"),
            ],
            synced=False,
        )
        text = "\n".join(eval_cli.lines(report, 0.9))
        assert "PASS  ok" in text
        assert "PASS* fixed" in text
        assert "· guard: x" in text
        assert "FAIL  bad" in text
        assert "'boom'" in text
        assert "langfuse off" in text
        assert eval_cli.run_name(datetime(2026, 11, 3, 18, 5, tzinfo=UTC)).startswith(
            "2026-11-03 18:05 system@"
        )

    async def test_run_filters_and_gates(self, tmp_path: Path) -> None:
        path = tmp_path / "set.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(c)
                for c in [
                    {"id": "hi", "kind": "smalltalk", "input": {"question": "Oi"}},
                    {"id": "other", "input": {"question": "Q"}},
                ]
            )
        )
        said: list[str] = []
        run = eval_cli.run
        now = datetime.now(UTC)
        code = await run(
            RunEval(agent("Olá!")),
            path,
            now=now,
            min_pass=1.0,
            only=["hi"],
            metadata={},
            say=said.append,
        )
        assert code == 0
        assert any("PASS  hi" in line for line in said)
        assert (
            await run(
                RunEval(agent()),
                path,
                now=now,
                min_pass=1.0,
                only=["ghost"],
                metadata={},
                say=said.append,
            )
            == 1
        )
        assert said[-1] == "No cases to run."
        failing = RunEval(Agent(ScriptedModel(fail=True), FakeKnowledge()))
        assert (
            await run(failing, path, now=now, min_pass=1.0, only=[], metadata={}, say=said.append)
            == 1
        )

    def test_the_command(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        path = tmp_path / "set.jsonl"
        path.write_text('{"id": "hi", "kind": "smalltalk", "input": {"question": "Oi"}}\n')
        world = make_world()
        world.model.replies = [say("Olá!")]
        seen: dict[str, Any] = {}

        class Infra:
            langfuse = None

        def build_infrastructure(settings: Any) -> Infra:
            seen["environment"] = settings.langfuse_environment
            return Infra()

        monkeypatch.setattr(cli, "build_infrastructure", build_infrastructure)
        monkeypatch.setattr(cli, "build_container", lambda _s, _i: world.container())
        for name, value in REQUIRED_SETTINGS.items():
            monkeypatch.setenv(name.upper(), str(value))
        assert cli.main(["eval", str(path), "--min-pass", "1"]) == 0
        assert seen["environment"] == "eval"
        assert world.closer.closed
