"""Rich output for runs. Cell text is passed as ``Text`` so brackets in model output
or case ids are never interpreted as markup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agentgauge.calibration import CalibrationReport
from agentgauge.compare import Comparison
from agentgauge.compare.format import (
    HEADLINES,
    LISTED_CASES,
    interval,
    percent,
    points,
    rule_sentence,
    summary_sentence,
)
from agentgauge.core.models import CaseResult, RunResult, Trajectory
from agentgauge.storage import RunSummary

ID_WIDTH = 8
KAPPA_TRUSTED = 0.6
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


def _clip(text: str, width: int = 100) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def _trajectory_lines(trajectory: Trajectory) -> list[Text]:
    lines: list[Text] = []
    step = 0
    for message in trajectory.messages:
        if message.role == "assistant":
            step += 1
            if message.content:
                lines.append(Text.assemble(f"  {step:>2}  assistant  ", _clip(message.content)))
            for call in message.tool_calls:
                lines.append(
                    Text.assemble(
                        f"  {step:>2}  ",
                        ("call", "cyan"),
                        f"       {call.name} {_clip(call.arguments)}",
                    )
                )
            if not message.content and not message.tool_calls:
                lines.append(Text(f"  {step:>2}  assistant  (empty reply)", style="dim"))
        else:
            lines.append(
                Text.assemble("      ", ("result", "green"), f"     {_clip(message.content)}")
            )
    return lines


def render_trajectories(console: Console, run: RunResult) -> None:
    """Print each case's agent steps: model text, tool calls, tool results and how it ended."""
    console.print(Text("Trajectories", style="bold"))
    for result in run.results:
        trajectory = result.output.trajectory if result.output else None
        if trajectory is None:
            console.print(Text(f"{result.case_id}: no trajectory recorded", style="dim"))
            continue
        console.print(
            Text.assemble(
                (result.case_id, "bold"),
                f"  {trajectory.steps} step(s), {len(trajectory.tool_calls)} tool call(s), "
                f"stopped: {trajectory.stop_reason}",
            )
        )
        for line in _trajectory_lines(trajectory):
            console.print(line)


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


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def kappa_warning(report: CalibrationReport) -> str | None:
    """A warning when kappa says the judge cannot be trusted, else ``None``."""
    if report.kappa is None:
        return (
            "kappa is undefined because the judge and the labels each used a single score "
            "throughout; this sample cannot show that the judge is trustworthy."
        )
    if report.kappa < KAPPA_TRUSTED:
        return (
            f"kappa {report.kappa:.2f} is below {KAPPA_TRUSTED}: this judge is not trustworthy "
            "against these labels. Revise the rubric or prompt, or use a stronger judge model, "
            "and calibrate again."
        )
    return None


def render_calibration(
    console: Console,
    report: CalibrationReport,
    *,
    suite_name: str,
    judge_model: str,
    skipped: Sequence[str] = (),
    unlabelled: int = 0,
) -> None:
    """Print a calibration report: headline numbers, confusion matrix, per-class table."""
    console.print(Text(f"calibration of {suite_name}  judge {judge_model}", style="bold"))
    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_row("cases compared", str(report.n))
    summary.add_row("accuracy", f"{report.accuracy:.2f}")
    kappa = "undefined" if report.kappa is None else f"{report.kappa:.2f}"
    if report.kappa_ci is not None:
        kappa += f"  (95% CI {report.kappa_ci[0]:.2f} to {report.kappa_ci[1]:.2f})"
    summary.add_row(f"kappa ({report.weighting} weighting)", kappa)
    console.print(summary)

    matrix = Table(title="Confusion matrix")
    matrix.add_column("human \\ judge")
    for label in report.classes:
        matrix.add_column(str(label), justify="right")
    for label, row in zip(report.classes, report.confusion, strict=True):
        matrix.add_row(str(label), *(str(count) for count in row))
    console.print(matrix)

    classes = Table(title="Per class (human label is truth)")
    for heading in ("score", "support", "precision", "recall"):
        classes.add_column(heading, justify="right")
    for stats in report.per_class:
        classes.add_row(
            str(stats.label), str(stats.support), _ratio(stats.precision), _ratio(stats.recall)
        )
    console.print(classes)

    if skipped:
        console.print(
            Text(f"{len(skipped)} labelled case(s) not compared (judge error): ", style="yellow")
            + Text(", ".join(skipped))
        )
    if unlabelled:
        console.print(f"{unlabelled} case(s) in the suite have no label and were ignored.")
    warning = kappa_warning(report)
    if warning is not None:
        console.print(Text("Warning: ", style="bold yellow") + Text(warning, style="yellow"))


_VERDICT_STYLE = {"regression": "bold red", "improvement": "bold green", "unchanged": "bold"}


def _case_line(label: str, case_ids: tuple[str, ...]) -> Text | None:
    if not case_ids:
        return None
    shown = ", ".join(case_ids[:LISTED_CASES])
    extra = len(case_ids) - LISTED_CASES
    return Text(f"{label} ({len(case_ids)}): {shown}" + (f" and {extra} more" if extra > 0 else ""))


def render_comparison(console: Console, c: Comparison) -> None:
    """Print a comparison: verdict, the change in words, a metrics table, and what moved."""
    console.print(
        Text.assemble(
            ("agentgauge compare: ", "bold"),
            (HEADLINES[c.verdict], _VERDICT_STYLE[c.verdict]),
            f"  suite {c.suite_name}",
        )
    )
    console.print(
        Text(
            f"baseline {c.baseline_id[:ID_WIDTH]} ({c.baseline_model})  "
            f"candidate {c.candidate_id[:ID_WIDTH]} ({c.candidate_model})"
        )
    )
    console.print(Text(summary_sentence(c)))
    table = Table()
    for heading in ("Metric", "Baseline", "Candidate", "Change (95% interval)"):
        table.add_column(heading)
    table.add_row(
        Text("pass rate"),
        Text(percent(c.baseline_pass_rate)),
        Text(percent(c.candidate_pass_rate)),
        Text(f"{points(c.delta)} ({interval(*c.delta_ci)})"),
    )
    for s in c.scorers:
        table.add_row(
            Text(f"{s.scorer} mean"),
            Text(f"{s.baseline_mean:.3f}"),
            Text(f"{s.candidate_mean:.3f}"),
            Text(f"{s.delta:+.3f} ({interval(*s.delta_ci, scale=1.0, digits=3)})"),
        )
    if c.baseline_latency_ms is not None and c.candidate_latency_ms is not None:
        table.add_row(
            Text("mean latency"),
            Text(f"{c.baseline_latency_ms:.0f} ms"),
            Text(f"{c.candidate_latency_ms:.0f} ms"),
            Text(f"{c.candidate_latency_ms - c.baseline_latency_ms:+.0f} ms"),
        )
    console.print(table)
    for line in (_case_line("Regressed", c.regressed), _case_line("Improved", c.improved)):
        if line is not None:
            console.print(line)
    for warning in c.warnings:
        console.print(Text("Warning: ", style="bold yellow") + Text(warning, style="yellow"))
    for label, left_out in (("baseline", c.only_in_baseline), ("candidate", c.only_in_candidate)):
        if left_out:
            console.print(
                Text(f"{len(left_out)} case(s) only in the {label} were left out.", style="dim")
            )
    console.print(Text(rule_sentence(c), style="dim"))
