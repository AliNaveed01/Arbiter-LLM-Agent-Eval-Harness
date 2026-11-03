import asyncio
from collections.abc import Iterator

import pytest

from agentgauge.core import ModelOutput, Score, ScorerSpec, TestCase
from agentgauge.scorers import (
    Scorer,
    ScorerConfigError,
    available_scorers,
    create_scorer,
    register_scorer,
    unregister_scorer,
)


class Fixed:
    name = "fixed"

    def __init__(self, value: float = 1.0) -> None:
        self.value = value

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        return Score(scorer=self.name, value=self.value, passed=self.value >= 0.5)


@pytest.fixture
def fixed() -> Iterator[None]:
    register_scorer("fixed")(Fixed)
    yield
    unregister_scorer("fixed")


@pytest.mark.usefixtures("fixed")
def test_registered_scorer_is_listed_and_created_by_name() -> None:
    assert "fixed" in available_scorers()
    scorer = create_scorer("fixed")
    assert isinstance(scorer, Scorer)
    case = TestCase(id="c", input="x")
    result = asyncio.run(scorer.score(case, ModelOutput(text="", latency_ms=0)))
    assert result.value == 1.0


@pytest.mark.usefixtures("fixed")
def test_params_are_passed_to_the_factory() -> None:
    scorer = create_scorer(ScorerSpec(name="fixed", params={"value": 0.25}))
    assert isinstance(scorer, Fixed)
    assert scorer.value == 0.25


def test_unknown_scorer_lists_available_names() -> None:
    with pytest.raises(ScorerConfigError, match="unknown scorer 'nope'; available:"):
        create_scorer("nope")


@pytest.mark.usefixtures("fixed")
def test_bad_params_raise_config_error() -> None:
    with pytest.raises(ScorerConfigError, match="invalid params for scorer 'fixed'"):
        create_scorer(ScorerSpec(name="fixed", params={"bogus": 1}))


@pytest.mark.usefixtures("fixed")
def test_duplicate_registration_is_rejected() -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_scorer("fixed")(Fixed)


def test_unregister_unknown_name_is_a_no_op() -> None:
    unregister_scorer("never-registered")


def test_unknown_scorer_message_when_registry_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentgauge.scorers.registry._REGISTRY", {})
    with pytest.raises(ScorerConfigError, match="none registered"):
        create_scorer("x")
