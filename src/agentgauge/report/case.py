"""The detail of one case: what the model said, how each scorer judged it, what went wrong."""

from __future__ import annotations

from agentgauge.core.models import CaseResult, Score, ToolCall, Trajectory
from agentgauge.report.html import Markup, join, tag


def case_status(result: CaseResult) -> tuple[str, str, str]:
    """The css class, icon and word for a case. The word and icon carry meaning, not colour."""
    if result.error is not None:
        return "error", "!", "error"
    return ("pass", "✓", "pass") if result.passed else ("fail", "✗", "fail")


def block(label: str, content: str) -> Markup:
    """A labelled, scrollable block of text. Long text is shown in full, never truncated."""
    return join([tag("div", label, class_="label"), tag("pre", content)])


def _score_row(score: Score) -> Markup:
    css, icon, word = ("pass", "✓", "pass") if score.passed else ("fail", "✗", "fail")
    return tag(
        "tr",
        tag("td", tag("code", score.scorer)),
        tag("td", f"{score.value:g}", class_="num"),
        tag("td", f"{icon} {word}", class_=f"status {css}"),
        tag("td", score.reason or ""),
    )


def scores_table(scores: tuple[Score, ...]) -> Markup:
    head = tag(
        "tr",
        tag("th", "Scorer"),
        tag("th", "Value", class_="num"),
        tag("th", "Result"),
        tag("th", "Reason"),
    )
    body = join(_score_row(s) for s in scores)
    return tag("div", tag("table", tag("thead", head), tag("tbody", body)), class_="scroll")


def tool_call_lines(calls: tuple[ToolCall, ...]) -> str:
    return "\n".join(f"{call.name} {call.arguments}" for call in calls)


def trajectory_section(trajectory: Trajectory) -> Markup:
    """The agent's steps in order: model text, tool calls, tool results, and how it ended."""
    steps: list[Markup] = []
    step = 0
    for message in trajectory.messages:
        if message.role == "assistant":
            step += 1
            lines = [message.content] if message.content else []
            lines += [f"-> {call.name} {call.arguments}" for call in message.tool_calls]
            content = "\n".join(lines) or "(empty reply)"
            steps.append(tag("div", block(f"Step {step}: model", content), class_="step"))
        else:
            steps.append(tag("div", block("Tool result", message.content), class_="step"))
    ended = (
        tag("span", "cut off at the step limit", class_="fail")
        if trajectory.stop_reason == "max_steps"
        else Markup("answered")
    )
    summary = tag(
        "p",
        f"{trajectory.steps} step(s), {len(trajectory.tool_calls)} tool call(s); ended: ",
        ended,
        class_="muted",
    )
    return join([tag("div", "Agent trajectory", class_="label"), summary, *steps])


def _metrics(result: CaseResult) -> str:
    parts: list[str] = []
    if result.latency_ms is not None:
        parts.append(f"{result.latency_ms:.0f} ms")
    output = result.output
    if output is not None and output.prompt_tokens is not None:
        parts.append(f"{output.prompt_tokens} prompt tokens")
    if output is not None and output.completion_tokens is not None:
        parts.append(f"{output.completion_tokens} completion tokens")
    if result.cost_usd is not None:
        parts.append(f"${result.cost_usd:.4f}")
    return ", ".join(parts)


def case_detail(index: int, result: CaseResult, *, expand: bool = False) -> Markup:
    """A collapsible section for ``result``, anchored as ``case-<index>``."""
    css, icon, word = case_status(result)
    summary = tag(
        "summary",
        tag("span", f"{icon} {word}", class_=f"status {css}"),
        " ",
        tag("code", result.case_id),
    )
    parts: list[Markup] = []
    if result.error is not None:
        parts.append(block("Error", result.error))
    output = result.output
    if output is not None:
        parts.append(block("Output", output.text or "(empty reply)"))
        if output.tool_calls:
            parts.append(block("Tool calls", tool_call_lines(output.tool_calls)))
    if output is not None and output.trajectory is not None:
        parts.append(trajectory_section(output.trajectory))
    if result.scores:
        parts.append(tag("div", "Scores", class_="label"))
        parts.append(scores_table(result.scores))
    if metrics := _metrics(result):
        parts.append(tag("p", metrics, class_="muted"))
    return tag(
        "details",
        summary,
        tag("div", join(parts), class_="body"),
        class_="case",
        id=f"case-{index}",
        open=expand,
    )
