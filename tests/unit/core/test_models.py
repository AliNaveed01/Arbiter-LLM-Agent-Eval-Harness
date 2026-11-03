from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from agentgauge.core import (
    CaseResult,
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    RunResult,
    Score,
    ScorerSpec,
    Suite,
    TestCase,
    ToolCall,
    ToolSpec,
)


def _output() -> ModelOutput:
    return ModelOutput(
        text="4", latency_ms=12.5, prompt_tokens=5, completion_tokens=1, cost_usd=0.0001
    )


def _score() -> Score:
    return Score(scorer="exact_match", value=1.0, passed=True)


def _case() -> TestCase:
    return TestCase(id="c1", input="2+2?", expected="4", metadata={"tag": "math"})


def _run() -> RunResult:
    ok = CaseResult(case_id="c1", output=_output(), scores=(_score(),))
    failed = CaseResult(case_id="c2", error="timeout")
    return RunResult(
        run_id="r1",
        suite_name="basic",
        model="fake",
        started_at=datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 11, 2, 12, 1, tzinfo=UTC),
        results=(ok, failed),
    )


def _request() -> CompletionRequest:
    return CompletionRequest(
        messages=(
            Message(role="system", content="be brief"),
            Message(role="user", content="weather?"),
            Message(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="c1", name="search", arguments="{}"),),
            ),
            Message(role="tool", content="sunny", tool_call_id="c1"),
        ),
        tools=(
            ToolSpec(
                name="search",
                description="Search the web",
                parameters={"type": "object", "properties": {"q": {"type": "string"}}},
            ),
        ),
        params=GenerationParams(temperature=0.2, max_tokens=64, seed=1, stop=("END",)),
    )


ALL: list[BaseModel] = [
    _request(),
    Message(role="user", content="hi"),
    ToolSpec(name="t", description="d"),
    ToolCall(id="c1", name="search", arguments='{"q": "x"}'),
    GenerationParams(temperature=0.5),
    ModelOutput(
        text="", latency_ms=1.0, tool_calls=(ToolCall(id="c1", name="search", arguments="{}"),)
    ),
    _case(),
    Suite(name="basic", cases=(_case(),), scorers=("exact_match",), description="d"),
    _output(),
    _score(),
    CaseResult(case_id="c1", output=_output(), scores=(_score(),)),
    _run(),
]


@pytest.mark.parametrize("model", ALL, ids=lambda m: type(m).__name__)
def test_json_round_trip(model: BaseModel) -> None:
    restored = type(model).model_validate_json(model.model_dump_json())
    assert restored == model


@pytest.mark.parametrize("model", ALL, ids=lambda m: type(m).__name__)
def test_models_are_frozen(model: BaseModel) -> None:
    field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError):
        setattr(model, field, "changed")


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        TestCase.model_validate({"id": "c1", "input": "x", "bogus": 1})


def test_negative_latency_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelOutput(text="x", latency_ms=-1)


def test_defaults_are_independent() -> None:
    a = TestCase(id="a", input="x")
    b = TestCase(id="b", input="y")
    assert a.metadata is not b.metadata


def test_string_input_becomes_single_user_message() -> None:
    case = TestCase(id="c", input="hello")
    assert case.input == (Message(role="user", content="hello"),)


def test_message_list_input_is_kept() -> None:
    messages = [Message(role="system", content="s"), Message(role="user", content="u")]
    case = TestCase(id="c", input=messages)
    assert case.input == tuple(messages)


def test_message_dicts_are_validated_from_data() -> None:
    case = TestCase.model_validate(
        {
            "id": "c",
            "input": [
                {"role": "user", "content": "u"},
                {"role": "tool", "content": "t", "tool_call_id": "1"},
            ],
        }
    )
    assert case.input[1].tool_call_id == "1"


def test_invalid_role_rejected() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate({"role": "robot", "content": "x"})


def test_generation_params_validation() -> None:
    with pytest.raises(ValidationError):
        GenerationParams(temperature=-0.1)
    with pytest.raises(ValidationError):
        GenerationParams(max_tokens=0)


def test_merged_over_overrides_field_by_field() -> None:
    defaults = GenerationParams(temperature=0.2, max_tokens=100, seed=7)
    merged = GenerationParams(temperature=0.9, stop=("END",)).merged_over(defaults)
    assert merged == GenerationParams(temperature=0.9, max_tokens=100, seed=7, stop=("END",))
    assert defaults.temperature == 0.2


def test_merged_over_without_defaults_returns_self() -> None:
    params = GenerationParams(seed=3)
    assert params.merged_over(None) is params


def test_assistant_message_may_carry_tool_calls() -> None:
    call = ToolCall(id="c1", name="search", arguments="{}")
    message = Message(role="assistant", content="", tool_calls=(call,))
    assert message.tool_calls == (call,)
    assert Message.model_validate_json(message.model_dump_json()) == message


@pytest.mark.parametrize("role", ["system", "user", "tool"])
def test_only_assistant_may_carry_tool_calls(role: str) -> None:
    call = {"id": "c1", "name": "search", "arguments": "{}"}
    data = {"role": role, "content": "x", "tool_call_id": "c1", "tool_calls": [call]}
    with pytest.raises(ValidationError, match="only assistant"):
        Message.model_validate(data)


def test_tool_message_requires_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="tool_call_id"):
        Message(role="tool", content="sunny")
    with pytest.raises(ValidationError, match="tool_call_id"):
        Message(role="tool", content="sunny", tool_call_id="")


def test_suite_scorers_accept_names_and_specs() -> None:
    suite = Suite.model_validate(
        {
            "name": "s",
            "cases": [],
            "scorers": ["exact_match", {"name": "regex", "params": {"pattern": "a+"}}],
        }
    )
    assert suite.scorers == (
        ScorerSpec(name="exact_match"),
        ScorerSpec(name="regex", params={"pattern": "a+"}),
    )
    assert Suite.model_validate_json(suite.model_dump_json()) == suite


def test_suite_scorers_constructor_accepts_strings() -> None:
    suite = Suite(name="s", cases=(), scorers=("contains", ScorerSpec(name="regex")))
    assert [s.name for s in suite.scorers] == ["contains", "regex"]


def test_suite_scorers_rejects_non_sequence() -> None:
    with pytest.raises(ValidationError):
        Suite.model_validate({"name": "s", "cases": [], "scorers": "exact_match"})


def test_case_result_records_latency_and_cost() -> None:
    result = CaseResult(case_id="c", output=_output(), latency_ms=12.5, cost_usd=0.001)
    assert (result.latency_ms, result.cost_usd) == (12.5, 0.001)
    assert CaseResult.model_validate_json(result.model_dump_json()) == result
    assert CaseResult(case_id="c").latency_ms is None


def test_case_result_rejects_negative_latency_and_cost() -> None:
    with pytest.raises(ValidationError):
        CaseResult(case_id="c", latency_ms=-1)
    with pytest.raises(ValidationError):
        CaseResult(case_id="c", cost_usd=-0.1)


def test_case_result_passed() -> None:
    good = Score(scorer="s", value=1.0, passed=True)
    bad = Score(scorer="s", value=0.0, passed=False)
    assert CaseResult(case_id="c", scores=(good, good)).passed
    assert not CaseResult(case_id="c", scores=(good, bad)).passed
    assert not CaseResult(case_id="c", scores=(good,), error="boom").passed
    assert CaseResult(case_id="c").passed
