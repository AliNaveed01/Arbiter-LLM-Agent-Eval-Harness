import asyncio
from collections.abc import Sequence

import pytest

from agentgauge.core import (
    AgentConfig,
    CompletionRequest,
    GenerationParams,
    ModelOutput,
    Score,
    Suite,
    TestCase,
    ToolCall,
    ToolMock,
    ToolSpec,
)
from agentgauge.runner import run_suite
from agentgauge.runner.agent import resolve_tool_call, run_agent
from agentgauge.scorers import register_scorer, unregister_scorer

WEATHER = ToolSpec(name="get_weather", description="Weather", parameters={"type": "object"})
MOCKS = (
    ToolMock(tool="get_weather", arguments={"city": "Paris"}, result="sunny, 21C"),
    ToolMock(tool="get_weather", result="no data"),
)


def call(call_id: str, name: str = "get_weather", arguments: str = '{"city": "Paris"}') -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


class Script:
    """A provider that replies with the given outputs in order and records requests."""

    name = "script"

    def __init__(self, outputs: Sequence[ModelOutput]) -> None:
        self._outputs = list(outputs)
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> ModelOutput:
        self.requests.append(request)
        return self._outputs.pop(0)


def out(
    text: str = "", *calls: ToolCall, latency: float = 10.0, **extra: float | int
) -> ModelOutput:
    return ModelOutput(text=text, latency_ms=latency, tool_calls=calls, **extra)  # type: ignore[arg-type]


CASE = TestCase(id="c", input="Weather in Paris?")


def run(provider: Script, max_steps: int = 8, **kwargs: object) -> ModelOutput:
    return asyncio.run(
        run_agent(
            provider,
            CASE,
            AgentConfig(max_steps=max_steps),
            tools=(WEATHER,),
            mocks=MOCKS,
            **kwargs,  # type: ignore[arg-type]
        )
    )


def test_tool_call_result_is_fed_back_and_the_answer_ends_the_loop() -> None:
    provider = Script([out("", call("1")), out("It is sunny and 21C.")])
    result = run(provider)
    assert result.text == "It is sunny and 21C."
    assert result.tool_calls == ()
    trajectory = result.trajectory
    assert trajectory is not None and trajectory.stop_reason == "final"
    assert [(m.role, m.content) for m in trajectory.messages] == [
        ("assistant", ""),
        ("tool", "sunny, 21C"),
        ("assistant", "It is sunny and 21C."),
    ]
    assert trajectory.messages[1].tool_call_id == "1"
    second = provider.requests[1]
    assert [m.role for m in second.messages] == ["user", "assistant", "tool"]
    assert second.messages[1].tool_calls == (call("1"),)
    assert all(request.tools == (WEATHER,) for request in provider.requests)


def test_a_model_that_answers_immediately_makes_one_step() -> None:
    result = run(Script([out("Paris is in France.")]))
    assert result.trajectory is not None
    assert (result.trajectory.steps, result.trajectory.tool_calls) == (1, ())


def test_parallel_calls_each_get_a_result() -> None:
    provider = Script([out("", call("a"), call("b", arguments='{"city": "Rome"}')), out("done")])
    result = run(provider)
    assert result.trajectory is not None
    results = [m for m in result.trajectory.messages if m.role == "tool"]
    assert [(m.tool_call_id, m.content) for m in results] == [("a", "sunny, 21C"), ("b", "no data")]


def test_the_loop_stops_at_max_steps() -> None:
    provider = Script([out("", call(str(i))) for i in range(5)])
    result = run(provider, max_steps=3)
    assert result.trajectory is not None
    assert (result.trajectory.stop_reason, result.trajectory.steps) == ("max_steps", 3)
    assert len(provider.requests) == 3


def test_latency_tokens_and_cost_are_summed_over_steps() -> None:
    provider = Script(
        [
            out("", call("1"), latency=10.0, prompt_tokens=5, completion_tokens=2, cost_usd=0.01),
            out("ok", latency=30.0, prompt_tokens=9, completion_tokens=1, cost_usd=0.02),
        ]
    )
    result = run(provider)
    assert result.latency_ms == 40.0
    assert (result.prompt_tokens, result.completion_tokens) == (14, 3)
    assert result.cost_usd == pytest.approx(0.03)


def test_missing_token_and_cost_figures_stay_missing() -> None:
    result = run(Script([out("ok")]))
    assert (result.prompt_tokens, result.completion_tokens, result.cost_usd) == (None, None, None)


def test_params_reach_every_step() -> None:
    provider = Script([out("", call("1")), out("ok")])
    run(provider, params=GenerationParams(temperature=0.0, seed=1))
    expected = GenerationParams(temperature=0.0, seed=1)
    assert [r.params for r in provider.requests] == [expected, expected]


def test_mock_resolution() -> None:
    assert resolve_tool_call(call("1"), MOCKS) == "sunny, 21C"
    assert resolve_tool_call(call("1", arguments='{"city": " paris "}'), MOCKS) == "sunny, 21C"
    assert resolve_tool_call(call("1", arguments='{"city": "Oslo"}'), MOCKS) == "no data"
    assert "no result is available for tool 'get_time'" in resolve_tool_call(
        call("1", "get_time"), MOCKS
    )
    assert "not a valid JSON object" in resolve_tool_call(call("1", arguments="{city"), MOCKS)
    assert resolve_tool_call(call("1", arguments='{"city": "Oslo"}'), MOCKS[:1]).startswith(
        "error:"
    )


def test_an_unanswerable_call_is_shown_to_the_model_and_the_run_continues() -> None:
    provider = Script([out("", call("1", "get_time", "{}")), out("I could not get the time.")])
    result = run(provider)
    assert result.trajectory is not None
    assert result.trajectory.messages[1].content.startswith("error: no result")
    assert result.text == "I could not get the time."


def test_run_suite_uses_the_loop_only_when_the_suite_has_an_agent_block() -> None:
    class Final:
        name = "final"

        async def score(self, case: TestCase, output: ModelOutput) -> Score:
            steps = output.trajectory.steps if output.trajectory else 0
            return Score(scorer="final", value=float(steps), passed=steps == 2)

    register_scorer("final")(Final)
    try:
        provider = Script([out("", call("1")), out("sunny")])
        agent = Suite(
            name="s",
            cases=(CASE,),
            scorers=("final",),
            tools=(WEATHER,),
            tool_mocks=MOCKS,
            agent=AgentConfig(),
        )
        result = asyncio.run(run_suite(agent, provider))
        (case_result,) = result.results
        assert case_result.passed and case_result.output is not None
        assert case_result.output.text == "sunny"
        assert case_result.latency_ms is not None

        plain = Suite(name="s", cases=(CASE,), scorers=("final",), tools=(WEATHER,))
        provider = Script([out("hello")])
        (plain_result,) = asyncio.run(run_suite(plain, provider)).results
        assert plain_result.output is not None and plain_result.output.trajectory is None
        assert not plain_result.passed
    finally:
        unregister_scorer("final")


def test_a_provider_error_inside_the_loop_is_a_case_error() -> None:
    class Failing(Script):
        async def complete(self, request: CompletionRequest) -> ModelOutput:
            if self.requests:
                raise RuntimeError("endpoint went away")
            self.requests.append(request)
            return out("", call("1"))

    suite = Suite(name="s", cases=(CASE,), tools=(WEATHER,), tool_mocks=MOCKS, agent=AgentConfig())
    (result,) = asyncio.run(run_suite(suite, Failing([]))).results
    assert result.error == "RuntimeError: endpoint went away"
