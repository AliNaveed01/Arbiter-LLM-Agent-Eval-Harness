import asyncio
from collections.abc import Iterator
from datetime import UTC

import anyio
import pytest

from agentgauge.core import (
    CompletionRequest,
    GenerationParams,
    ModelOutput,
    Score,
    ScorerSpec,
    Suite,
    TestCase,
)
from agentgauge.providers import FakeProvider
from agentgauge.runner import run_suite
from agentgauge.scorers import ScorerConfigError, register_scorer, unregister_scorer


def make_suite(n: int = 3, scorers: tuple[str | ScorerSpec, ...] = ("exact_match",)) -> Suite:
    cases = tuple(TestCase(id=f"c{i}", input=f"q{i}", expected=f"a{i}") for i in range(n))
    return Suite(name="s", cases=cases, scorers=scorers)


def answers(n: int = 3) -> FakeProvider:
    return FakeProvider({f"q{i}": f"a{i}" for i in range(n)}, name="fake-model")


class Boom:
    name = "boom"

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        raise RuntimeError("scorer exploded")


@pytest.fixture
def boom() -> Iterator[None]:
    register_scorer("boom")(Boom)
    yield
    unregister_scorer("boom")


class Tracking:
    """Provider that records how many calls are in flight at once."""

    name = "tracking"

    def __init__(self, delays: dict[str, float] | None = None) -> None:
        self.delays = delays or {}
        self.in_flight = 0
        self.max_in_flight = 0

    async def complete(self, request: CompletionRequest) -> ModelOutput:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            text = request.messages[-1].content
            await anyio.sleep(self.delays.get(text, 0.01))
            return ModelOutput(text=text, latency_ms=0)
        finally:
            self.in_flight -= 1


def test_runs_and_scores_every_case_in_suite_order() -> None:
    result = asyncio.run(run_suite(make_suite(), answers()))
    assert [r.case_id for r in result.results] == ["c0", "c1", "c2"]
    assert all(r.passed for r in result.results)
    assert result.results[1].scores[0].scorer == "exact_match"
    assert result.results[1].output is not None
    assert result.results[1].output.text == "a1"


def test_run_metadata() -> None:
    first = asyncio.run(run_suite(make_suite(), answers()))
    second = asyncio.run(run_suite(make_suite(), answers()))
    assert first.run_id != second.run_id
    assert (first.suite_name, first.model) == ("s", "fake-model")
    assert first.started_at.tzinfo is UTC
    assert first.finished_at is not None
    assert first.finished_at >= first.started_at


def test_failed_scores_are_recorded_not_raised() -> None:
    provider = FakeProvider({"q0": "wrong", "q1": "a1"})
    result = asyncio.run(run_suite(make_suite(2), provider))
    assert [r.passed for r in result.results] == [False, True]
    assert result.results[0].error is None


def test_multiple_scorers_apply_to_each_case() -> None:
    suite = make_suite(1, scorers=("exact_match", "contains"))
    result = asyncio.run(run_suite(suite, answers(1)))
    assert [s.scorer for s in result.results[0].scores] == ["exact_match", "contains"]


def test_suite_without_scorers_still_runs() -> None:
    result = asyncio.run(run_suite(make_suite(2, scorers=()), answers(2)))
    assert [r.scores for r in result.results] == [(), ()]
    assert all(r.output is not None for r in result.results)


def test_empty_suite() -> None:
    result = asyncio.run(run_suite(make_suite(0), answers(0)))
    assert result.results == ()


def test_unknown_scorer_fails_before_any_case_runs() -> None:
    provider = answers()
    with pytest.raises(ScorerConfigError, match="unknown scorer 'nope'"):
        asyncio.run(run_suite(make_suite(scorers=("nope",)), provider))
    assert provider.calls == []


def test_generation_params_reach_the_provider() -> None:
    provider = answers(1)
    params = GenerationParams(temperature=0.3)
    asyncio.run(run_suite(make_suite(1), provider, params=params))
    assert provider.calls[0].params == params
    assert provider.calls[0].messages == make_suite(1).cases[0].input


@pytest.mark.parametrize("limit", [1, 3, 8])
def test_concurrency_limit_is_respected_and_used(limit: int) -> None:
    provider = Tracking()
    suite = make_suite(12, scorers=())
    asyncio.run(run_suite(suite, provider, concurrency=limit))
    assert provider.max_in_flight == limit


def test_default_concurrency_is_eight() -> None:
    provider = Tracking()
    asyncio.run(run_suite(make_suite(20, scorers=()), provider))
    assert provider.max_in_flight == 8


def test_limit_larger_than_suite_runs_everything_at_once() -> None:
    provider = Tracking()
    asyncio.run(run_suite(make_suite(3, scorers=()), provider, concurrency=10))
    assert provider.max_in_flight == 3


def test_results_keep_suite_order_when_cases_finish_out_of_order() -> None:
    provider = Tracking(delays={"q0": 0.05, "q1": 0.0, "q2": 0.02})
    result = asyncio.run(run_suite(make_suite(3, scorers=()), provider))
    assert [r.case_id for r in result.results] == ["c0", "c1", "c2"]


@pytest.mark.parametrize("bad", [0, -1])
def test_concurrency_must_be_positive(bad: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        asyncio.run(run_suite(make_suite(), answers(), concurrency=bad))


def test_provider_failure_is_recorded_and_the_run_continues() -> None:
    provider = FakeProvider(
        {"q0": "a0", "q2": "a2"}, errors={"q1": TimeoutError("upstream timed out")}
    )
    result = asyncio.run(run_suite(make_suite(), provider))
    failed = result.results[1]
    assert failed.error == "TimeoutError: upstream timed out"
    assert failed.output is None
    assert failed.scores == ()
    assert not failed.passed
    assert [result.results[0].passed, result.results[2].passed] == [True, True]


def test_exception_without_message_is_still_described() -> None:
    result = asyncio.run(run_suite(make_suite(1), FakeProvider(errors={"q0": KeyError()})))
    assert result.results[0].error == "KeyError"


def test_every_case_failing_still_returns_a_result() -> None:
    provider = FakeProvider(errors={f"q{i}": RuntimeError("down") for i in range(3)})
    result = asyncio.run(run_suite(make_suite(), provider))
    assert [r.error for r in result.results] == ["RuntimeError: down"] * 3


@pytest.mark.usefixtures("boom")
def test_broken_scorer_fails_the_case_but_keeps_other_scores() -> None:
    suite = make_suite(2, scorers=("boom", "exact_match"))
    result = asyncio.run(run_suite(suite, answers(2)))
    for case_result in result.results:
        assert case_result.error == "scorer 'boom' failed: RuntimeError: scorer exploded"
        assert [s.scorer for s in case_result.scores] == ["exact_match"]
        assert case_result.output is not None
        assert not case_result.passed


def test_latency_is_measured_per_case() -> None:
    ticks = iter([10.0, 10.25])
    result = asyncio.run(run_suite(make_suite(1), answers(1), clock=lambda: next(ticks)))
    assert result.results[0].latency_ms == pytest.approx(250.0)


def test_latency_is_recorded_for_failed_cases() -> None:
    ticks = iter([5.0, 5.5])
    provider = FakeProvider(errors={"q0": RuntimeError("x")})
    result = asyncio.run(run_suite(make_suite(1), provider, clock=lambda: next(ticks)))
    assert result.results[0].latency_ms == pytest.approx(500.0)


def test_cost_is_copied_from_the_output() -> None:
    class Priced:
        name = "priced"

        async def complete(self, request: CompletionRequest) -> ModelOutput:
            return ModelOutput(text="a0", latency_ms=1, cost_usd=0.0042)

    result = asyncio.run(run_suite(make_suite(1), Priced()))
    assert result.results[0].cost_usd == 0.0042


def test_cost_is_none_when_the_provider_reports_none() -> None:
    class Unpriced:
        name = "unpriced"

        async def complete(self, request: CompletionRequest) -> ModelOutput:
            return ModelOutput(text="a0", latency_ms=1)

    assert asyncio.run(run_suite(make_suite(1), Unpriced())).results[0].cost_usd is None


def test_cancellation_is_not_swallowed() -> None:
    class Hangs:
        name = "hangs"

        async def complete(self, request: CompletionRequest) -> ModelOutput:
            await anyio.sleep(10)
            raise AssertionError("unreachable")

    async def go() -> bool:
        with anyio.move_on_after(0.05) as scope:
            await run_suite(make_suite(2), Hangs())
        return scope.cancelled_caught

    assert asyncio.run(go()) is True


class Closable:
    name = "closable"
    closed = 0

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        return Score(scorer=self.name, value=1.0, passed=True)

    async def aclose(self) -> None:
        type(self).closed += 1


def test_scorers_with_aclose_are_closed_after_the_run() -> None:
    Closable.closed = 0
    register_scorer("closable")(Closable)
    try:
        asyncio.run(run_suite(make_suite(scorers=("closable",)), answers()))
    finally:
        unregister_scorer("closable")
    assert Closable.closed == 1
