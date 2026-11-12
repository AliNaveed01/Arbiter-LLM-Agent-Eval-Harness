"""The run section of a report: a summary and a table of its cases."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from agentgauge.core.models import CaseResult, RunResult
from agentgauge.report.html import Markup, join, tag
from agentgauge.report.page import Theme, page

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


def _scores(result: CaseResult) -> str:
    return ", ".join(f"{s.scorer} {s.value:g}" for s in result.scores) or "-"


def _reason(result: CaseResult) -> str:
    """Why the case did not pass: its error, or the first failing score's reason."""
    if result.error is not None:
        return result.error
    for score in result.scores:
        if not score.passed:
            return f"{score.scorer}: {score.reason}" if score.reason else score.scorer
    return ""


def cases_table(run: RunResult) -> Markup:
    """One row per case: status, scores, latency and the reason it failed."""
    if not run.results:
        return tag("p", "No cases.", class_="muted")
    head = tag(
        "tr",
        tag("th", "Case"),
        tag("th", "Result"),
        tag("th", "Scores"),
        tag("th", "Latency", class_="num"),
        tag("th", "Reason"),
    )
    rows: list[Markup] = []
    for result in run.results:
        css, icon, word = case_status(result)
        latency = f"{result.latency_ms:.0f} ms" if result.latency_ms is not None else "-"
        rows.append(
            tag(
                "tr",
                tag("td", tag("code", result.case_id)),
                tag("td", f"{icon} {word}", class_=f"status {css}"),
                tag("td", _scores(result)),
                tag("td", latency, class_="num"),
                tag("td", _reason(result)),
            )
        )
    return tag("div", tag("table", tag("thead", head), tag("tbody", join(rows))), class_="scroll")


def render_run_report(run: RunResult, *, theme: Theme = "auto") -> str:
    """The whole report page for one run."""
    body = join([run_summary(run), tag("h2", "Cases"), cases_table(run)])
    return page(f"agentgauge run {run.suite_name}", body, theme=theme)
