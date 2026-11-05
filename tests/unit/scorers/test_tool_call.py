import asyncio
import json
from typing import Any

import pytest

from agentgauge.core.models import ModelOutput, ScorerSpec, TestCase, ToolCall
from agentgauge.scorers import ScorerConfigError, ToolCallScorer, create_scorer

WEATHER = {"name": "get_weather", "arguments": {"city": "Paris"}}


def case(expected: Any = WEATHER, key: str = "expected_tool_call") -> TestCase:
    return TestCase(id="c", input="q", metadata={key: expected})


def call(name: str = "get_weather", arguments: Any = None) -> ToolCall:
    if arguments is None:
        arguments = {"city": "Paris"}
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(id="1", name=name, arguments=text)


def output(*calls: ToolCall) -> ModelOutput:
    return ModelOutput(text="", latency_ms=0.0, tool_calls=calls)


def run(test_case: TestCase, out: ModelOutput) -> tuple[bool, str]:
    score = asyncio.run(ToolCallScorer().score(test_case, out))
    assert score.value == (1.0 if score.passed else 0.0)
    return score.passed, score.details["outcome"]


def test_right_tool_and_arguments_pass() -> None:
    assert run(case(), output(call())) == (True, "ok")


def test_string_arguments_ignore_case_and_whitespace_but_numbers_are_exact() -> None:
    assert run(case(), output(call(arguments={"city": " paris "}))) == (True, "ok")
    expected = {"name": "add", "arguments": {"a": 1, "b": 2}}
    assert run(case(expected), output(call("add", {"a": 1.0, "b": 2}))) == (True, "ok")
    assert run(case(expected), output(call("add", {"a": 1, "b": 3}))) == (False, "wrong_arguments")


def test_each_failure_has_its_own_outcome() -> None:
    assert run(case(), output()) == (False, "no_call")
    assert run(case(), output(call(), call())) == (False, "extra_calls")
    assert run(case(), output(call("get_time"))) == (False, "wrong_tool")
    assert run(case(), output(call(arguments={"city": "Rome"}))) == (False, "wrong_arguments")
    assert run(case(), output(call(arguments={}))) == (False, "wrong_arguments")
    assert run(case(), output(call(arguments={"city": "Paris", "x": 1}))) == (
        False,
        "wrong_arguments",
    )


@pytest.mark.parametrize("arguments", ["{city: Paris", "not json", "[1, 2]", '"Paris"'])
def test_malformed_arguments_are_reported_not_repaired(arguments: str) -> None:
    assert run(case(), output(call(arguments=arguments))) == (False, "malformed_arguments")


def test_a_case_that_expects_no_call() -> None:
    assert run(case(None), output()) == (True, "ok")
    assert run(case(None), output(call())) == (False, "unexpected_call")


def test_missing_or_invalid_expectation() -> None:
    bare = TestCase(id="c", input="q")
    assert run(bare, output(call())) == (False, "missing_expectation")
    with pytest.raises(ScorerConfigError, match="must be null or have a 'name'"):
        run(case({"arguments": {}}), output(call()))
    with pytest.raises(ScorerConfigError):
        run(case("get_weather"), output(call()))


def test_expected_arguments_default_to_empty_and_key_is_configurable() -> None:
    assert run(case({"name": "ping"}), output(call("ping", {}))) == (True, "ok")
    scorer = create_scorer(ScorerSpec(name="tool_call", params={"key": "want"}))
    result = asyncio.run(scorer.score(case(WEATHER, key="want"), output(call())))
    assert result.passed
