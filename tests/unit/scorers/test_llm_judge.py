import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from agentgauge.core.models import (
    CompletionRequest,
    GenerationParams,
    ModelOutput,
    ProviderConfig,
    ScorerSpec,
    TestCase,
)
from agentgauge.judge import Rubric, render_prompt
from agentgauge.scorers import JudgeError, LLMJudge, ScorerConfigError, create_scorer

RUBRIC: dict[str, Any] = {"name": "quality", "criteria": ["is correct"], "scale": 5}
CASE = TestCase(id="c", input="What is 2 + 2?", expected="4")
OUTPUT = ModelOutput(text="4", latency_ms=1.0)


class Scripted:
    """A provider that replies with the given texts in order."""

    def __init__(self, replies: Sequence[str], name: str = "judge-model") -> None:
        self._replies = list(replies)
        self._name = name
        self.requests: list[CompletionRequest] = []
        self.closed = False

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: CompletionRequest) -> ModelOutput:
        self.requests.append(request)
        return ModelOutput(text=self._replies.pop(0), latency_ms=0.0)

    async def aclose(self) -> None:
        self.closed = True


def _judge(replies: Sequence[str], **kwargs: Any) -> tuple[LLMJudge, Scripted]:
    provider = Scripted(replies)
    return LLMJudge(RUBRIC, provider=provider, **kwargs), provider


def test_scores_a_valid_verdict_and_records_provenance() -> None:
    judge, provider = _judge(['{"score": 4, "reasoning": "correct"}'])
    score = asyncio.run(judge.score(CASE, OUTPUT))
    assert (score.scorer, score.value, score.passed) == ("llm_judge", 4.0, True)
    assert score.reason == "correct"
    assert score.details == {
        "judge_model": "judge-model",
        "rubric": "quality",
        "prompt_version": "v1",
        "scale": {"kind": "ordinal", "levels": 5},
        "raw_output": '{"score": 4, "reasoning": "correct"}',
        "attempts": 1,
    }
    assert len(provider.requests) == 1
    assert provider.requests[0].messages == render_prompt(Rubric.model_validate(RUBRIC), CASE, "4")


def test_score_below_threshold_fails() -> None:
    judge, _ = _judge(['{"score": 2, "reasoning": "weak"}'])
    assert not asyncio.run(judge.score(CASE, OUTPUT)).passed


def test_judge_runs_at_temperature_zero_unless_told_otherwise() -> None:
    judge, provider = _judge(['{"score": 4, "reasoning": "r"}'])
    asyncio.run(judge.score(CASE, OUTPUT))
    assert provider.requests[0].params == GenerationParams(temperature=0.0)
    judge, provider = _judge(
        ['{"score": 4, "reasoning": "r"}'], params=GenerationParams(temperature=0.5, seed=7)
    )
    asyncio.run(judge.score(CASE, OUTPUT))
    assert provider.requests[0].params == GenerationParams(temperature=0.5, seed=7)


def test_malformed_reply_is_retried_once_and_the_retry_is_recorded() -> None:
    judge, provider = _judge(["I think it is a 4", '{"score": 4, "reasoning": "fine"}'])
    score = asyncio.run(judge.score(CASE, OUTPUT))
    assert score.value == 4.0
    assert score.details["attempts"] == 2
    assert score.details["raw_output"] == '{"score": 4, "reasoning": "fine"}'
    retry = provider.requests[1].messages
    assert retry[-2].role == "assistant"
    assert retry[-2].content == "I think it is a 4"
    assert retry[-1].role == "user"
    assert "not valid JSON" in retry[-1].content


def test_two_malformed_replies_raise_with_the_raw_reply() -> None:
    judge, provider = _judge(["nope", '{"score": 9, "reasoning": "r"}'])
    with pytest.raises(JudgeError, match=r"invalid after one retry.*outside the scale.*score"):
        asyncio.run(judge.score(CASE, OUTPUT))
    assert len(provider.requests) == 2


def test_binary_rubric_value_is_zero_or_one() -> None:
    provider = Scripted(['{"score": 0, "reasoning": "wrong"}'])
    judge = LLMJudge({**RUBRIC, "scale": "binary"}, provider=provider)
    score = asyncio.run(judge.score(CASE, OUTPUT))
    assert (score.value, score.passed) == (0.0, False)


def test_aclose_closes_the_provider_when_it_can() -> None:
    judge, provider = _judge([])
    asyncio.run(judge.aclose())
    assert provider.closed


def test_registry_builds_a_judge_from_yaml_style_params() -> None:
    key = render_prompt(Rubric.model_validate(RUBRIC), CASE, "4")[1].content
    spec = ScorerSpec(
        name="llm_judge",
        params={
            "rubric": RUBRIC,
            "judge": {
                "type": "fake",
                "model": "fake-judge",
                "responses": {key: '{"score": 5, "reasoning": "yes"}'},
            },
        },
    )
    score = asyncio.run(create_scorer(spec).score(CASE, OUTPUT))
    assert (score.value, score.details["judge_model"]) == (5.0, "fake-judge")


def test_rubric_may_be_a_path(tmp_path: Path) -> None:
    path = tmp_path / "rubric.yaml"
    path.write_text("name: q\ncriteria: [c]\nscale: binary\n", encoding="utf-8")
    judge = LLMJudge(str(path), provider=Scripted([]))
    assert judge is not None


def test_a_rubric_instance_and_a_provider_config_are_accepted() -> None:
    config = ProviderConfig(type="fake", model="j", responses={})
    judge = LLMJudge(Rubric.model_validate(RUBRIC), config)
    assert asyncio.run(judge.aclose()) is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rubric": {"name": "q"}, "provider": Scripted([])}, "rubric is invalid"),
        ({"rubric": "missing.yaml", "provider": Scripted([])}, "cannot read file"),
        ({"rubric": RUBRIC}, "exactly one of"),
        ({"rubric": RUBRIC, "judge": {"type": "fake"}, "provider": Scripted([])}, "exactly one of"),
        ({"rubric": RUBRIC, "judge": {"type": "nope"}}, "judge is invalid"),
    ],
)
def test_configuration_errors(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ScorerConfigError, match=message):
        LLMJudge(**kwargs)
