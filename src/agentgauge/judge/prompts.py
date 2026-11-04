"""Versioned judge prompt templates and the code that renders them.

Templates use ``$name`` placeholders (``string.Template``), so JSON braces in a
template need no escaping. The system message is fixed: it carries the reply
format the verdict parser depends on, so a custom template cannot break it. A
template only controls the user message.
"""

from __future__ import annotations

from string import Template
from typing import TYPE_CHECKING

from agentgauge.core.models import Message, TestCase

if TYPE_CHECKING:
    from agentgauge.judge.rubric import Rubric

PLACEHOLDERS = frozenset({"rubric", "criteria", "scale", "input", "expected", "output"})

SYSTEM_PROMPT = (
    "You are an impartial evaluator. Judge the response against the criteria and reply "
    'with only a JSON object of the form {"score": <integer>, "reasoning": "<one or two '
    'sentences>"}. Do not add any other text.'
)

TEMPLATES: dict[str, str] = {
    "v1": (
        "Rubric: $rubric\n\n"
        "Criteria:\n$criteria\n\n"
        "Score: $scale\n\n"
        "Conversation:\n$input\n\n"
        "Reference answer:\n$expected\n\n"
        "Response to judge:\n$output"
    ),
}


def template_problem(version: str, custom: str | None) -> str | None:
    """Why a rubric's template is unusable, or ``None`` when it is fine."""
    if custom is None:
        if version not in TEMPLATES:
            known = ", ".join(sorted(TEMPLATES))
            return f"unknown prompt_version {version!r}; built-in versions: {known}"
        return None
    try:
        unknown = Template(custom).get_identifiers()
        invalid = not Template(custom).is_valid()
    except ValueError as exc:  # pragma: no cover - get_identifiers never raises on 3.12
        return f"invalid template: {exc}"
    if invalid:
        return "invalid template: stray '$'; write '$$' for a literal dollar sign"
    extra = sorted(set(unknown) - PLACEHOLDERS)
    if extra:
        return f"unknown placeholders {extra}; allowed: {sorted(PLACEHOLDERS)}"
    return None


def describe_scale(rubric: Rubric) -> str:
    if rubric.scale.kind == "binary":
        return "0 (fails the criteria) or 1 (meets them)"
    return f"an integer from 1 (worst) to {rubric.scale.levels} (best)"


def render_prompt(rubric: Rubric, case: TestCase, output_text: str) -> tuple[Message, ...]:
    """The system and user messages that ask the judge to score ``output_text``."""
    source = rubric.template if rubric.template is not None else TEMPLATES[rubric.prompt_version]
    user = Template(source).substitute(
        rubric=rubric.name,
        criteria="\n".join(f"- {item}" for item in rubric.criteria),
        scale=describe_scale(rubric),
        input="\n".join(f"{m.role}: {m.content}" for m in case.input),
        expected=case.expected if case.expected is not None else "(none given)",
        output=output_text,
    )
    return (Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user))
