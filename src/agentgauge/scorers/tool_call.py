"""The ``tool_call`` scorer: did the model call the right tool with the right arguments?"""

from __future__ import annotations

import json
from typing import Any

from agentgauge.core.models import ModelOutput, Score, TestCase, ToolCall
from agentgauge.scorers.arguments import same_arguments
from agentgauge.scorers.registry import ScorerConfigError, register_scorer

NAME = "tool_call"


@register_scorer(NAME)
class ToolCallScorer:
    """Checks the model's tool call against ``case.metadata[key]``.

    The expectation is either ``{"name": ..., "arguments": {...}}`` (the model
    must make exactly one call, to that tool, with equal arguments) or ``null``
    (the model must not call any tool). String arguments are compared ignoring
    case and edge whitespace. Arguments that are not a JSON object are reported
    as ``malformed_arguments`` and never repaired.

    ``Score.details["outcome"]`` says what happened: ``ok``, ``no_call``,
    ``unexpected_call``, ``extra_calls``, ``wrong_tool``, ``wrong_arguments`` or
    ``malformed_arguments``.
    """

    name = NAME

    def __init__(self, key: str = "expected_tool_call") -> None:
        self._key = key

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        if self._key not in case.metadata:
            return _result(False, "case has no expected tool call", "missing_expectation")
        expected: Any = case.metadata[self._key]
        calls: tuple[ToolCall, ...] = output.tool_calls
        if expected is None:
            if calls:
                reason = f"expected no tool call, got {calls[0].name!r}"
                return _result(False, reason, "unexpected_call")
            return _result(True, None, "ok")
        if not isinstance(expected, dict) or "name" not in expected:
            raise ScorerConfigError(f"{self._key} must be null or have a 'name'")
        return _check_call(expected, calls)  # pyright: ignore[reportUnknownArgumentType]


def _check_call(expected: dict[str, Any], calls: tuple[ToolCall, ...]) -> Score:
    if len(calls) != 1:
        if not calls:
            return _result(False, "no tool call", "no_call")
        return _result(False, f"expected one tool call, got {len(calls)}", "extra_calls")
    (call,) = calls
    if call.name != expected["name"]:
        return _result(False, f"called {call.name!r}, expected {expected['name']!r}", "wrong_tool")
    try:
        arguments: Any = json.loads(call.arguments)
    except json.JSONDecodeError:
        reason = f"arguments are not valid JSON: {call.arguments!r}"
        return _result(False, reason, "malformed_arguments")
    if not isinstance(arguments, dict):
        reason = f"arguments are not a JSON object: {call.arguments!r}"
        return _result(False, reason, "malformed_arguments")
    wanted: Any = expected.get("arguments", {})
    if not same_arguments(arguments, wanted):
        return _result(False, f"arguments {arguments!r}, expected {wanted!r}", "wrong_arguments")
    return _result(True, None, "ok")


def _result(passed: bool, reason: str | None, outcome: str) -> Score:
    return Score(
        scorer=NAME,
        value=1.0 if passed else 0.0,
        passed=passed,
        reason=reason,
        details={"outcome": outcome},
    )
