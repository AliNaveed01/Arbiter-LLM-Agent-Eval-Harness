"""The run section of a report: a summary and a table of its cases."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from agentgauge.core.models import CaseResult, RunResult
from agentgauge.report.html import Markup, join, tag

ID_WIDTH = 8


def moment(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def duration(run: RunResult) -> str | None:
    if run.finished_at is None:
        return None
    return f"{(run.finished_at - run.started_at).total_seconds():.2f} s"


def _stat(label: str, value: str) -> Markup:
    return tag("li", tag("b", value), label)


def run_summary(run: RunResult) -> Markup:
    """Title, identity and the headline numbers of ``run``."""
    errored = sum(1 for r in run.results if r.error is not None)
    passed = sum(1 for r in run.results if r.passed)
    total = len(run.results)
    failed = total - passed - errored
    latencies = [r.latency_ms for r in run.results if r.latency_ms is not None]
    costs = [r.cost_usd for r in run.results if r.cost_usd is not None]
    facts = [
        f"model {run.model}",
        f"run {run.run_id[:ID_WIDTH]}",
        f"started {moment(run.started_at)}",
    ]
    if (took := duration(run)) is not None:
        facts.append(f"took {took}")
    stats = [
        _stat("cases", str(total)),
        _stat("passed", str(passed)),
        _stat("failed", str(failed)),
        _stat("errors", str(errored)),
        _stat("pass rate", f"{passed / total:.0%}" if total else "n/a"),
    ]
    if latencies:
        stats.append(_stat("mean latency", f"{statistics.fmean(latencies):.0f} ms"))
    if costs:
        stats.append(_stat("cost", f"${sum(costs):.4f}"))
    return join(
        [
            tag("h1", f"Run report: {run.suite_name}"),
            tag("p", ", ".join(facts), class_="muted"),
            tag("ul", join(stats), class_="stats"),
        ]
    )


def case_status(result: CaseResult) -> tuple[str, str, str]:
    """The css class, icon and word for a case. The word and icon carry meaning, not colour."""
    if result.error is not None:
        return "error", "!", "error"
    return ("pass", "✓", "pass") if result.passed else ("fail", "✗", "fail")
