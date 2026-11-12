"""The comparison section of a report. Numbers come from the same helpers as the CLI's."""

from __future__ import annotations

from collections.abc import Mapping

from agentgauge.compare import Comparison
from agentgauge.compare.format import (
    HEADLINES,
    ID_WIDTH,
    LISTED_CASES,
    interval,
    latency_change,
    percent,
    points,
    rule_sentence,
    summary_sentence,
)
from agentgauge.report.chart import change_chart
from agentgauge.report.html import Markup, join, tag

_VERDICT = {
    "regression": ("fail", "✗"),
    "improvement": ("pass", "✓"),
    "unchanged": ("muted", "="),
}


def _case_link(case_id: str, anchors: Mapping[str, int]) -> Markup:
    code = tag("code", case_id)
    return tag("a", code, href=f"#case-{anchors[case_id]}") if case_id in anchors else code


def _case_list(label: str, case_ids: tuple[str, ...], anchors: Mapping[str, int]) -> Markup | None:
    if not case_ids:
        return None
    shown = join((_case_link(c, anchors) for c in case_ids[:LISTED_CASES]), ", ")
    extra = len(case_ids) - LISTED_CASES
    more = f" and {extra} more" if extra > 0 else ""
    return tag("p", tag("b", f"{label} ({len(case_ids)}): "), shown, more)


def _metric_rows(c: Comparison) -> list[Markup]:
    def row(name: Markup, before: str, after: str, change: str) -> Markup:
        return tag(
            "tr",
            tag("td", name),
            tag("td", before, class_="num"),
            tag("td", after, class_="num"),
            tag("td", change),
        )

    rows = [
        row(
            Markup("pass rate"),
            percent(c.baseline_pass_rate),
            percent(c.candidate_pass_rate),
            f"{points(c.delta)} ({interval(*c.delta_ci)})",
        )
    ]
    for s in c.scorers:
        rows.append(
            row(
                join([tag("code", s.scorer), " mean score"]),
                f"{s.baseline_mean:.3f}",
                f"{s.candidate_mean:.3f}",
                f"{s.delta:+.3f} ({interval(*s.delta_ci, scale=1.0, digits=3)})",
            )
        )
    if c.baseline_latency_ms is not None and c.candidate_latency_ms is not None:
        rows.append(
            row(
                Markup("mean latency"),
                f"{c.baseline_latency_ms:.0f} ms",
                f"{c.candidate_latency_ms:.0f} ms",
                latency_change(c.baseline_latency_ms, c.candidate_latency_ms),
            )
        )
    return rows


def comparison_section(c: Comparison, anchors: Mapping[str, int] | None = None) -> Markup:
    """Verdict, the change in words, the metrics, and the cases that moved."""
    links = anchors or {}
    css, icon = _VERDICT[c.verdict]
    head = tag(
        "tr",
        tag("th", "Metric"),
        tag("th", "Baseline", class_="num"),
        tag("th", "Candidate", class_="num"),
        tag("th", "Change (95% interval)"),
    )
    table = tag(
        "div",
        tag("table", tag("thead", head), tag("tbody", join(_metric_rows(c)))),
        class_="scroll",
    )
    notes = list(c.warnings)
    if c.only_in_baseline:
        notes.append(f"{len(c.only_in_baseline)} case(s) only in the baseline were left out")
    if c.only_in_candidate:
        notes.append(f"{len(c.only_in_candidate)} case(s) only in the candidate were left out")
    parts: list[Markup | None] = [
        tag("h2", "Comparison"),
        tag("p", tag("span", f"{icon} {HEADLINES[c.verdict]}", class_=f"status {css}")),
        tag(
            "p",
            f"baseline {c.baseline_id[:ID_WIDTH]} ({c.baseline_model}) against candidate "
            f"{c.candidate_id[:ID_WIDTH]} ({c.candidate_model})",
            class_="muted",
        ),
        tag("p", summary_sentence(c)),
        change_chart(c),
        table,
        _case_list("Regressed", c.regressed, links),
        _case_list("Improved", c.improved, links),
        *[tag("p", f"Note: {note}", class_="muted") for note in notes],
        tag("p", rule_sentence(c), class_="muted"),
    ]
    return join(part for part in parts if part is not None)
