"""Render a :class:`Comparison` as markdown or JSON. Pure functions, no I/O."""

from __future__ import annotations

from agentgauge.compare.report import Comparison

LISTED_CASES = 20
ID_WIDTH = 8

HEADLINES = {
    "regression": "REGRESSION",
    "improvement": "Improvement",
    "unchanged": "No significant change",
}


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def points(value: float) -> str:
    """A pass-rate difference in percentage points, always signed."""
    return f"{value * 100:+.1f} points"


def latency_change(baseline_ms: float, candidate_ms: float) -> str:
    """The latency change in whole milliseconds, signed, never ``-0``."""
    return f"{round(candidate_ms - baseline_ms):+d} ms"


def interval(
    low: float, high: float, *, scale: float = 100.0, digits: int = 1, unit: str = ""
) -> str:
    return f"{low * scale:+.{digits}f} to {high * scale:+.{digits}f}{unit}"


def summary_sentence(c: Comparison) -> str:
    """One sentence stating the change, its interval and the p-value, without hedging."""
    direction = "fell" if c.delta < 0 else "rose" if c.delta > 0 else "did not change"
    movement = (
        f"Pass rate {direction} from {percent(c.baseline_pass_rate)} to "
        f"{percent(c.candidate_pass_rate)}"
        if c.delta != 0
        else f"Pass rate did not change ({percent(c.baseline_pass_rate)})"
    )
    return (
        f"{movement} ({points(c.delta)}, 95% interval "
        f"{interval(*c.delta_ci, unit=' points')}) over {c.cases} paired case(s); "
        f"exact McNemar p = {c.p_value:.3g}."
    )


def rule_sentence(c: Comparison) -> str:
    return (
        f"A regression needs p < {c.alpha:g} and a drop of more than "
        f"{c.max_drop * 100:g} points in pass rate."
    )


def _code(text: str) -> str:
    return "`" + text.replace("`", "'") + "`"


def _case_list(label: str, case_ids: tuple[str, ...]) -> list[str]:
    if not case_ids:
        return []
    shown = ", ".join(_code(case_id) for case_id in case_ids[:LISTED_CASES])
    extra = len(case_ids) - LISTED_CASES
    more = f" and {extra} more" if extra > 0 else ""
    return [f"**{label} ({len(case_ids)}):** {shown}{more}", ""]


def to_markdown(c: Comparison) -> str:
    """A GitHub-flavoured markdown report, suitable for a job summary or a PR comment."""
    lines = [
        f"### agentgauge: {HEADLINES[c.verdict]}",
        "",
        f"Suite `{c.suite_name}`: baseline {_code(c.baseline_id[:ID_WIDTH])} "
        f"({_code(c.baseline_model)}) against candidate {_code(c.candidate_id[:ID_WIDTH])} "
        f"({_code(c.candidate_model)}).",
        "",
        summary_sentence(c),
        "",
        "| Metric | Baseline | Candidate | Change (95% interval) |",
        "| --- | --- | --- | --- |",
        f"| Pass rate | {percent(c.baseline_pass_rate)} | {percent(c.candidate_pass_rate)} | "
        f"{points(c.delta)} ({interval(*c.delta_ci)}) |",
    ]
    for s in c.scorers:
        lines.append(
            f"| {_code(s.scorer)} mean score | {s.baseline_mean:.3f} | {s.candidate_mean:.3f} | "
            f"{s.delta:+.3f} ({interval(*s.delta_ci, scale=1.0, digits=3)}) |"
        )
    if c.baseline_latency_ms is not None and c.candidate_latency_ms is not None:
        lines.append(
            f"| Mean latency | {c.baseline_latency_ms:.0f} ms | {c.candidate_latency_ms:.0f} ms | "
            f"{latency_change(c.baseline_latency_ms, c.candidate_latency_ms)} |"
        )
    lines.append("")
    lines += _case_list("Regressed", c.regressed)
    lines += _case_list("Improved", c.improved)
    notes = list(c.warnings)
    if c.only_in_baseline:
        notes.append(f"{len(c.only_in_baseline)} case(s) only in the baseline were left out")
    if c.only_in_candidate:
        notes.append(f"{len(c.only_in_candidate)} case(s) only in the candidate were left out")
    lines += [f"- {note}" for note in notes]
    if notes:
        lines.append("")
    lines.append(f"_{rule_sentence(c)}_")
    return "\n".join(lines) + "\n"


def to_json(c: Comparison) -> str:
    """The full comparison as indented JSON, verdict included."""
    return c.model_dump_json(indent=2) + "\n"
