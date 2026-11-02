from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from agentgauge.core import CaseResult, ModelOutput, RunResult, Score, Suite, TestCase


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


ALL: list[BaseModel] = [
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
