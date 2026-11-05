import asyncio
import json
from typing import Any

import pytest

from agentgauge.core import Message, ModelOutput, Score, TestCase, ToolCall, Trajectory
from agentgauge.scorers import ScorerConfigError, TrajectoryBudget, TrajectoryMatch


def trajectory(*calls: tuple[str, dict[str, Any]], stop: str = "final") -> Trajectory:
    messages: list[Message] = []
    for i, (name, arguments) in enumerate(calls):
        call = ToolCall(id=str(i), name=name, arguments=json.dumps(arguments))
        messages.append(Message(role="assistant", content="", tool_calls=(call,)))
        messages.append(Message(role="tool", content="ok", tool_call_id=str(i)))
    messages.append(Message(role="assistant", content="done"))
    return Trajectory(messages=tuple(messages), stop_reason=stop)  # type: ignore[arg-type]


def output(t: Trajectory | None) -> ModelOutput:
    return ModelOutput(text="done", latency_ms=1.0, trajectory=t)


def case(expected: Any) -> TestCase:
    return TestCase(id="c", input="q", metadata={"expected_trajectory": expected})


SEARCH = {"name": "search", "arguments": {"q": "cats"}}
OPEN = {"name": "open", "arguments": {"id": 7}}
S = ("search", {"q": "cats"})
O = ("open", {"id": 7})  # noqa: E741


def score(mode: str, expected: Any, t: Trajectory | None, **kwargs: Any) -> Score:
    scorer = TrajectoryMatch(mode=mode, **kwargs)  # type: ignore[arg-type]
    return asyncio.run(scorer.score(case(expected), output(t)))


def test_exact_requires_the_same_calls_and_nothing_extra() -> None:
    assert score("exact", [SEARCH, OPEN], trajectory(S, O)).passed
    assert not score("exact", [SEARCH, OPEN], trajectory(O, S)).passed
    extra = score("exact", [SEARCH], trajectory(S, O))
    assert not extra.passed and "got ['search', 'open']" in (extra.reason or "")
    assert not score("exact", [SEARCH, OPEN], trajectory(S)).passed


def test_in_order_allows_extra_calls_between_but_not_reordering() -> None:
    assert score("in_order", [SEARCH, OPEN], trajectory(S, ("noop", {}), O)).passed
    reordered = score("in_order", [SEARCH, OPEN], trajectory(O, S))
    assert not reordered.passed and reordered.value == 0.5
    assert score("in_order", [SEARCH, OPEN], trajectory(S)).value == 0.5


def test_any_order_ignores_order_and_counts_each_call_once() -> None:
    assert score("any_order", [SEARCH, OPEN], trajectory(O, S)).passed
    twice = score("any_order", [SEARCH, SEARCH], trajectory(S))
    assert not twice.passed and twice.value == 0.5


def test_default_mode_is_in_order() -> None:
    result = asyncio.run(TrajectoryMatch().score(case([SEARCH, OPEN]), output(trajectory(S, O))))
    assert result.passed and result.details["mode"] == "in_order"


def test_arguments_are_checked_unless_turned_off() -> None:
    wrong_args = trajectory(("search", {"q": "dogs"}), O)
    assert not score("in_order", [SEARCH, OPEN], wrong_args).passed
    assert score("in_order", [SEARCH, OPEN], wrong_args, check_args=False).passed
    assert score("in_order", [SEARCH], trajectory(("search", {"q": " CATS "}))).passed
    bad_json = Trajectory(
        messages=(
            Message(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="1", name="search", arguments="{q"),),
            ),
        )
    )
    assert not score("in_order", [SEARCH], bad_json).passed
    assert score("in_order", [SEARCH], bad_json, check_args=False).passed


def test_names_only_expectations_and_empty_expectations() -> None:
    assert score("in_order", [{"name": "ping"}], trajectory(("ping", {}))).passed
    assert not score("in_order", [{"name": "ping"}], trajectory(("ping", {"x": 1}))).passed
    assert score("in_order", [], trajectory(S)).passed
    assert score("any_order", [], trajectory()).value == 1.0
    assert score("exact", [], trajectory()).passed
    assert not score("exact", [], trajectory(S)).passed


def test_details_record_what_was_expected_and_seen() -> None:
    result = score("in_order", [SEARCH, OPEN], trajectory(S))
    assert result.details == {
        "mode": "in_order",
        "expected": ["search", "open"],
        "actual": ["search"],
        "matched": 1,
    }


def test_no_trajectory_and_no_expectation_fail_clearly() -> None:
    assert "no trajectory" in (score("in_order", [SEARCH], None).reason or "")
    bare = asyncio.run(TrajectoryMatch().score(TestCase(id="c", input="q"), output(trajectory())))
    assert not bare.passed and "no expected trajectory" in (bare.reason or "")


@pytest.mark.parametrize("bad", ["search", [{"arguments": {}}], [1], {"name": "x"}])
def test_invalid_expectations_are_configuration_errors(bad: Any) -> None:
    with pytest.raises(ScorerConfigError, match="must be a list"):
        score("in_order", bad, trajectory(S))


def test_invalid_mode_is_a_configuration_error() -> None:
    with pytest.raises(ScorerConfigError, match="mode must be one of"):
        TrajectoryMatch(mode="sorted")  # type: ignore[arg-type]


def budget(max_calls: int, t: Trajectory | None, **kwargs: Any) -> Score:
    return asyncio.run(TrajectoryBudget(max_calls, **kwargs).score(case([]), output(t)))


def test_budget_counts_calls_and_requires_finishing() -> None:
    assert budget(2, trajectory(S, O)).passed
    over = budget(1, trajectory(S, O))
    assert not over.passed and "2 tool calls, budget is 1" in (over.reason or "")
    cut_off = budget(5, trajectory(S, stop="max_steps"))
    assert not cut_off.passed and "did not finish" in (cut_off.reason or "")
    assert budget(5, trajectory(S, stop="max_steps"), require_final=False).passed
    assert budget(0, trajectory()).details == {"calls": 0, "stop_reason": "final"}


def test_budget_without_trajectory_and_invalid_budget() -> None:
    assert "no trajectory" in (budget(1, None).reason or "")
    with pytest.raises(ScorerConfigError):
        TrajectoryBudget(-1)
