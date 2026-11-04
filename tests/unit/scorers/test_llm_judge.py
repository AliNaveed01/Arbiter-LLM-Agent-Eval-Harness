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
from agentgauge.judge import JudgeCache, Rubric, cache_key, render_prompt
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
    return LLMJudge(RUBRIC, provider=provider, **{"cache": False, **kwargs}), provider


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
        "cached": False,
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
    judge = LLMJudge({**RUBRIC, "scale": "binary"}, provider=provider, cache=False)
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
            "cache": False,
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
    judge = LLMJudge(str(path), provider=Scripted([]), cache=False)
    assert judge is not None


def test_a_rubric_instance_and_a_provider_config_are_accepted() -> None:
    config = ProviderConfig(type="fake", model="j", responses={})
    judge = LLMJudge(Rubric.model_validate(RUBRIC), config, cache=False)
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


GOOD = '{"score": 4, "reasoning": "correct"}'


def test_second_run_is_served_from_the_cache_with_the_same_score() -> None:
    cache = JudgeCache()
    first, provider = _judge([GOOD], cache=cache)
    one = asyncio.run(first.score(CASE, OUTPUT))
    second = LLMJudge(RUBRIC, provider=Scripted([]), cache=cache)  # would fail if it called
    two = asyncio.run(second.score(CASE, OUTPUT))
    assert len(provider.requests) == 1
    assert (two.value, two.passed, two.reason) == (one.value, one.passed, one.reason)
    assert two.details["raw_output"] == one.details["raw_output"]
    assert (one.details["cached"], two.details["cached"]) == (False, True)
    assert two.details["attempts"] == 0


def test_a_retried_reply_is_cached_under_the_original_prompt() -> None:
    cache = JudgeCache()
    first, _ = _judge(["garbage", GOOD], cache=cache)
    asyncio.run(first.score(CASE, OUTPUT))
    second = LLMJudge(RUBRIC, provider=Scripted([]), cache=cache)
    assert asyncio.run(second.score(CASE, OUTPUT)).value == 4.0


def test_a_failed_judgement_is_not_cached() -> None:
    cache = JudgeCache()
    judge, _ = _judge(["no", "still no"], cache=cache)
    with pytest.raises(JudgeError):
        asyncio.run(judge.score(CASE, OUTPUT))
    assert len(cache) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"params": GenerationParams(temperature=0.5)},
        {"rubric": {**RUBRIC, "prompt_version": "v1", "criteria": ["is concise"]}},
    ],
)
def test_changing_params_or_the_rubric_misses_the_cache(change: dict[str, Any]) -> None:
    cache = JudgeCache()
    asyncio.run(_judge([GOOD], cache=cache)[0].score(CASE, OUTPUT))
    provider = Scripted([GOOD])
    kwargs: dict[str, Any] = {"rubric": RUBRIC, "provider": provider, "cache": cache, **change}
    asyncio.run(LLMJudge(**kwargs).score(CASE, OUTPUT))
    assert len(provider.requests) == 1
    assert len(cache) == 2


def test_a_different_judge_model_misses_the_cache() -> None:
    cache = JudgeCache()
    asyncio.run(_judge([GOOD], cache=cache)[0].score(CASE, OUTPUT))
    other = Scripted([GOOD], name="another-judge")
    asyncio.run(LLMJudge(RUBRIC, provider=other, cache=cache).score(CASE, OUTPUT))
    assert len(other.requests) == 1


def test_an_unusable_cached_reply_is_treated_as_a_miss() -> None:
    cache = JudgeCache()
    judge, provider = _judge([GOOD], cache=cache)
    key = cache_key(
        "judge-model",
        GenerationParams(temperature=0.0),
        "v1",
        render_prompt(Rubric.model_validate(RUBRIC), CASE, "4"),
    )
    cache.put(key, "corrupt")
    assert asyncio.run(judge.score(CASE, OUTPUT)).value == 4.0
    assert len(provider.requests) == 1


def test_cache_false_always_calls_the_judge() -> None:
    judge, provider = _judge([GOOD, GOOD])
    asyncio.run(judge.score(CASE, OUTPUT))
    asyncio.run(judge.score(CASE, OUTPUT))
    assert len(provider.requests) == 2


def test_cache_path_is_opened_and_closed_by_the_scorer(tmp_path: Path) -> None:
    path = tmp_path / "judge.db"
    judge = LLMJudge(RUBRIC, provider=Scripted([GOOD]), cache=str(path))
    asyncio.run(judge.score(CASE, OUTPUT))
    asyncio.run(judge.aclose())
    with JudgeCache(path) as cache:
        assert len(cache) == 1


def test_a_shared_cache_is_not_closed_by_the_scorer() -> None:
    cache = JudgeCache()
    judge, _ = _judge([], cache=cache)
    asyncio.run(judge.aclose())
    assert len(cache) == 0  # still open


def test_default_cache_lives_under_dot_agentgauge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    judge = LLMJudge(RUBRIC, provider=Scripted([GOOD]))
    asyncio.run(judge.score(CASE, OUTPUT))
    asyncio.run(judge.aclose())
    assert (tmp_path / ".agentgauge" / "judge-cache.db").exists()


def test_unopenable_cache_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ScorerConfigError, match="cache"):
        LLMJudge(RUBRIC, provider=Scripted([]), cache=tmp_path)
