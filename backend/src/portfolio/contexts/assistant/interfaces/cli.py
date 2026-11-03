"""`portfolio eval`: runs the dataset through the agent, prints the report, gates."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from portfolio.contexts.assistant.application.evals import EvalCase, Report, RunEval
from portfolio.contexts.assistant.domain import prompts


def load(path: Path) -> list[EvalCase]:
    """One JSON object per line; blank lines and `//` comments are skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        EvalCase.parse(json.loads(line))
        for line in lines
        if line.strip() and not line.lstrip().startswith("//")
    ]


def run_name(now: datetime) -> str:
    return f"{now:%Y-%m-%d %H:%M} {prompts.load('system').version}"


def lines(report: Report, min_pass: float) -> list[str]:
    out = [f"run {report.run}", ""]
    for o in report.outcomes:
        # PASS* : it passed after a rewrite; the notes say what the first draft got wrong.
        mark = ("PASS" if o.first_pass else "PASS*") if o.passed else "FAIL"
        failed = f"  ✗ {', '.join(o.failed_checks)}" if o.failed_checks else ""
        out.append(
            f"{mark:<5} {o.case.id:<16} {o.latency_s:>5.1f}s ${o.cost_usd:.5f}  "
            f"{' > '.join(o.steps)}{failed}"
        )
        if not o.passed or not o.first_pass:
            out += [f"      · {note[:200]}" for note in o.notes]
        if not o.passed:
            out.append(f"      {(o.error or o.answer)[:220]!r}")
    out.append("")
    for name, rate in sorted(report.check_rates().items()):
        out.append(f"  {name:<18} {rate:>6.1%}")
    out += [
        "",
        f"passed {report.pass_rate:.1%} (gate {min_pass:.0%}) · "
        f"first pass {report.first_pass_rate:.1%} · leaks {len(report.leaks)} · "
        f"p50 {report.latency(0.5):.1f}s · p95 {report.latency(0.95):.1f}s · "
        f"${report.cost:.4f} · langfuse {'synced' if report.synced else 'off'}",
    ]
    return out


async def run(
    evaluate: RunEval,
    path: Path,
    *,
    now: datetime,
    min_pass: float,
    only: list[str],
    metadata: dict[str, Any],
    say: Callable[[str], None],
) -> int:
    cases = load(path)
    if only:
        cases = [case for case in cases if case.id in only]
    if not cases:
        say("No cases to run.")
        return 1
    report = await evaluate(path.stem, cases, run_name(now), metadata)
    for line in lines(report, min_pass):
        say(line)
    return 0 if report.gate(min_pass) else 1
