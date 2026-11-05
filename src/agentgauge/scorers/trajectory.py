"""Trajectory scorers: judge the sequence of tool calls an agent made, not just its answer."""

from __future__ import annotations

from typing import Any, Literal

from agentgauge.core.models import ModelOutput, Score, TestCase, ToolCall, Trajectory
from agentgauge.scorers.arguments import parse_arguments, same_arguments
from agentgauge.scorers.registry import ScorerConfigError, register_scorer

Mode = Literal["exact", "in_order", "any_order"]
MODES = ("exact", "in_order", "any_order")
NO_TRAJECTORY = "output has no trajectory (give the suite an 'agent' block, or import a trace)"


def _failure(scorer: str, reason: str, details: dict[str, Any] | None = None) -> Score:
    return Score(scorer=scorer, value=0.0, passed=False, reason=reason, details=details or {})


def _names(items: list[dict[str, Any]] | tuple[ToolCall, ...]) -> list[str]:
    return [item["name"] if isinstance(item, dict) else item.name for item in items]


@register_scorer("trajectory_match")
class TrajectoryMatch:
    """Compares the agent's tool calls with ``case.metadata[key]``.

    The expectation is a list of ``{name, arguments}`` (``arguments`` optional). ``mode``:

    * ``exact``: the same calls in the same order, no extras.
    * ``in_order`` (default): the expected calls appear in order; other calls may sit between.
    * ``any_order``: every expected call was made, in any order; extras are allowed.

    With ``check_args`` (default) arguments must be equal, strings ignoring case and edge
    whitespace; without it only tool names are compared. The score is the fraction of
    expected calls matched (1.0 or 0.0 for ``exact``); it passes only when all were.
    """

    name = "trajectory_match"

    def __init__(
        self, mode: Mode = "in_order", check_args: bool = True, key: str = "expected_trajectory"
    ) -> None:
        if mode not in MODES:
            raise ScorerConfigError(f"mode must be one of {list(MODES)}, got {mode!r}")
        self._mode = mode
        self._check_args = check_args
        self._key = key

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        if self._key not in case.metadata:
            return _failure(self.name, "case has no expected trajectory")
        expected = self._expected(case.metadata[self._key])
        if output.trajectory is None:
            return _failure(self.name, NO_TRAJECTORY)
        actual = output.trajectory.tool_calls
        matched = self._count(expected, actual)
        passed = matched == len(expected) and (self._mode != "exact" or len(actual) == matched)
        if self._mode == "exact":
            value = 1.0 if passed else 0.0
        else:
            value = matched / len(expected) if expected else 1.0
        details: dict[str, Any] = {
            "mode": self._mode,
            "expected": _names(expected),
            "actual": _names(actual),
            "matched": matched,
        }
        reason = None
        if not passed:
            reason = (
                f"expected calls {_names(expected)} ({self._mode}), got {_names(actual)}"
                f"; matched {matched}/{len(expected)}"
            )
        return Score(scorer=self.name, value=value, passed=passed, reason=reason, details=details)

    def _expected(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or not all(
            isinstance(item, dict) and "name" in item
            for item in raw  # pyright: ignore[reportUnknownVariableType]
        ):
            raise ScorerConfigError(f"{self._key} must be a list of {{name, arguments}} mappings")
        return list(raw)  # pyright: ignore[reportUnknownArgumentType]

    def _same(self, expected: dict[str, Any], call: ToolCall) -> bool:
        if call.name != expected["name"]:
            return False
        if not self._check_args:
            return True
        arguments = parse_arguments(call.arguments)
        return arguments is not None and same_arguments(arguments, expected.get("arguments", {}))

    def _count(self, expected: list[dict[str, Any]], actual: tuple[ToolCall, ...]) -> int:
        if self._mode == "exact":
            aligned = 0
            for want, got in zip(expected, actual, strict=False):
                if not self._same(want, got):
                    break
                aligned += 1
            return aligned
        if self._mode == "in_order":
            index = 0
            for call in actual:
                if index < len(expected) and self._same(expected[index], call):
                    index += 1
            return index
        remaining = list(actual)
        matched = 0
        for want in expected:
            for position, call in enumerate(remaining):
                if self._same(want, call):
                    del remaining[position]
                    matched += 1
                    break
        return matched


@register_scorer("trajectory_budget")
class TrajectoryBudget:
    """Passes when the agent made at most ``max_calls`` tool calls and finished.

    ``require_final`` (default) also fails an agent that was cut off at ``max_steps``
    while still calling tools.
    """

    name = "trajectory_budget"

    def __init__(self, max_calls: int, require_final: bool = True) -> None:
        if max_calls < 0:
            raise ScorerConfigError("max_calls must be at least 0")
        self._max_calls = max_calls
        self._require_final = require_final

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        trajectory: Trajectory | None = output.trajectory
        if trajectory is None:
            return _failure(self.name, NO_TRAJECTORY)
        calls = len(trajectory.tool_calls)
        details: dict[str, Any] = {"calls": calls, "stop_reason": trajectory.stop_reason}
        problems: list[str] = []
        if calls > self._max_calls:
            problems.append(f"{calls} tool calls, budget is {self._max_calls}")
        if self._require_final and trajectory.stop_reason != "final":
            problems.append("the agent did not finish within max_steps")
        if problems:
            return _failure(self.name, "; ".join(problems), details)
        return Score(scorer=self.name, value=1.0, passed=True, details=details)
