"""Rich output for runs. Cell text is passed as ``Text`` so brackets in model output
or case ids are never interpreted as markup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agentgauge.core.models import CaseResult, RunResult
from agentgauge.storage import RunSummary

ID_WIDTH = 8
OUTPUT_PREVIEW = 60


@dataclass(frozen=True)
class RunStats:
    total: int
    passed: int
    failed: int
    errored: int
    cost_usd: float | None
    duration_s: float | None


def summarize(run: RunResult) -> RunStats:
    """Count outcomes: ``errored`` cases raised, ``failed`` ones scored badly."""
    errored = sum(1 for r in run.results if r.error is not None)
    passed = sum(1 for r in run.results if r.passed)
    costs = [r.cost_usd for r in run.results if r.cost_usd is not None]
    duration = (run.finished_at - run.started_at).total_seconds() if run.finished_at else None
    return RunStats(
        total=len(run.results),
        passed=passed,
        failed=len(run.results) - passed - errored,
        errored=errored,
        cost_usd=sum(costs) if costs else None,
        duration_s=duration,
    )


def _moment(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _status(result: CaseResult) -> Text:
    if result.error is not None:
        return Text("ERROR", style="bold red")
    return Text("PASS", style="green") if result.passed else Text("FAIL", style="red")


def _detail(result: CaseResult) -> str:
    if result.error is not None:
        return result.error
    for score in result.scores:
        if not score.passed:
            return f"{score.scorer}: {score.reason}" if score.reason else score.scorer
    return ""


def render_run(console: Console, run: RunResult, *, verbose: bool = False) -> None:
    """Print a run header, a per-case table and a one-line summary."""
    console.print(
        Text.assemble(
            ("Run ", "bold"),
            (run.run_id[:ID_WIDTH], "cyan"),
            f"  suite {run.suite_name}  model {run.model}  started {_moment(run.started_at)}",
        )
    )
    table = Table(show_lines=False)
    table.add_column("Case")
    table.add_column("Result")
    table.add_column("Scores")
    table.add_column("Latency", justify="right")
    if verbose:
        table.add_column("Output")
    table.add_column("Detail")
    for result in run.results:
        scores = ", ".join(f"{s.scorer}={'pass' if s.passed else 'fail'}" for s in result.scores)
        latency = f"{result.latency_ms:.0f} ms" if result.latency_ms is not None else "-"
        cells: list[Text] = [
            Text(result.case_id),
            _status(result),
            Text(scores or "-"),
            Text(latency),
        ]
        if verbose:
            cells.append(Text(_preview(result)))
        cells.append(Text(_detail(result)))
        table.add_row(*cells)
    console.print(table)
    console.print(_summary_line(summarize(run)))


def _preview(result: CaseResult) -> str:
    if result.output is None:
        return "-"
    text = " ".join(result.output.text.split())
    return text if len(text) <= OUTPUT_PREVIEW else text[: OUTPUT_PREVIEW - 1] + "…"


def _summary_line(stats: RunStats) -> Text:
    line = Text(f"{stats.passed}/{stats.total} passed", style="bold")
    line.append(f", {stats.failed} failed, {stats.errored} errors")
    if stats.cost_usd is not None:
        line.append(f", cost ${stats.cost_usd:.4f}")
    if stats.duration_s is not None:
        line.append(f", took {stats.duration_s:.2f}s")
    return line


def render_run_list(console: Console, summaries: Sequence[RunSummary]) -> None:
    """Print a table of stored runs, or a hint when there are none."""
    if not summaries:
        console.print("No runs stored yet. Run a suite with: agentgauge run SUITE")
        return
    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Suite")
    table.add_column("Model")
    table.add_column("Started")
    table.add_column("Cases", justify="right")
    table.add_column("Passed", justify="right")
    table.add_column("Errors", justify="right")
    for s in summaries:
        table.add_row(
            Text(s.run_id[:ID_WIDTH]),
            Text(s.suite_name),
            Text(s.model),
            Text(_moment(s.started_at)),
            Text(str(s.total_cases)),
            Text(str(s.passed_cases)),
            Text(str(s.errored_cases)),
        )
    console.print(table)
