from agentgauge.core.models import CaseResult, Message, ModelOutput, Score, ToolCall, Trajectory
from agentgauge.report.case import (
    block,
    case_detail,
    scores_table,
    tool_call_lines,
    trajectory_section,
)

HOSTILE = "<script>alert(1)</script>"


def full_result() -> CaseResult:
    output = ModelOutput(
        text="Paris, of course.",
        latency_ms=42.0,
        prompt_tokens=12,
        completion_tokens=5,
        tool_calls=(ToolCall(id="1", name="get_weather", arguments='{"city": "Paris"}'),),
    )
    scores = (
        Score(scorer="contains", value=1.0, passed=True),
        Score(scorer="regex", value=0.0, passed=False, reason="no match"),
    )
    return CaseResult(
        case_id="capital", output=output, scores=scores, latency_ms=42.0, cost_usd=0.001
    )


def test_detail_shows_output_tool_calls_scores_and_metrics() -> None:
    out = case_detail(3, full_result())
    assert out.startswith('<details class="case" id="case-3">')
    assert "<pre>Paris, of course.</pre>" in out
    assert '<pre>get_weather {"city": "Paris"}</pre>'.replace('"', "&quot;") in out
    assert "<td>no match</td>" in out and '<td class="num">0</td>' in out
    assert "42 ms, 12 prompt tokens, 5 completion tokens, $0.0010" in out


def test_summary_carries_status_icon_word_and_case_id() -> None:
    out = case_detail(0, full_result())
    assert '<summary><span class="status fail">✗ fail</span> <code>capital</code></summary>' in out


def test_a_case_can_start_open_for_printing() -> None:
    assert " open>" in case_detail(0, full_result(), expand=True)
    assert " open" not in case_detail(0, full_result()).split(">")[0]


def test_an_error_and_an_empty_reply_are_stated_plainly() -> None:
    errored = case_detail(0, CaseResult(case_id="e", error="HTTP 500"))
    assert "<pre>HTTP 500</pre>" in errored and "Output" not in errored
    empty = case_detail(0, CaseResult(case_id="e", output=ModelOutput(text="", latency_ms=1)))
    assert "<pre>(empty reply)</pre>" in empty


def test_long_text_is_kept_whole() -> None:
    long = "x" * 50_000
    assert long in block("Output", long)


def test_everything_from_the_model_is_escaped() -> None:
    output = ModelOutput(
        text=HOSTILE,
        latency_ms=1,
        tool_calls=(ToolCall(id="1", name=HOSTILE, arguments=HOSTILE),),
    )
    result = CaseResult(
        case_id=HOSTILE,
        output=output,
        error=HOSTILE,
        scores=(Score(scorer=HOSTILE, value=0, passed=False, reason=HOSTILE),),
    )
    out = case_detail(0, result)
    assert "<script" not in out
    assert out.count("&lt;script&gt;") >= 7


def test_helpers() -> None:
    assert (
        tool_call_lines(
            (ToolCall(id="1", name="a", arguments="{}"), ToolCall(id="2", name="b", arguments="1"))
        )
        == "a {}\nb 1"
    )
    assert "<tbody></tbody>" in scores_table(())


def agent_trajectory(stop: str = "final") -> Trajectory:
    call = ToolCall(id="c1", name="get_weather", arguments='{"city": "Paris"}')
    return Trajectory(
        messages=(
            Message(role="assistant", content="Let me check.", tool_calls=(call,)),
            Message(role="tool", content="sunny, 21C", tool_call_id="c1"),
            Message(role="assistant", content="It is sunny in Paris."),
        ),
        stop_reason=stop,  # type: ignore[arg-type]
    )


def test_the_trajectory_shows_every_step_in_order() -> None:
    out = trajectory_section(agent_trajectory())
    assert "2 step(s), 1 tool call(s); ended: answered" in out
    positions = [
        out.index(marker)
        for marker in (
            "Step 1: model",
            "Let me check.",
            "-&gt; get_weather {&quot;city&quot;: &quot;Paris&quot;}",
            "Tool result",
            "sunny, 21C",
            "Step 2: model",
            "It is sunny in Paris.",
        )
    ]
    assert positions == sorted(positions)


def test_a_run_cut_off_at_the_step_limit_says_so() -> None:
    out = trajectory_section(agent_trajectory("max_steps"))
    assert '<span class="fail">cut off at the step limit</span>' in out


def test_an_empty_step_is_shown_as_empty() -> None:
    out = trajectory_section(Trajectory(messages=(Message(role="assistant", content=""),)))
    assert "<pre>(empty reply)</pre>" in out


def test_trajectory_text_is_escaped() -> None:
    call = ToolCall(id="c", name=HOSTILE, arguments=HOSTILE)
    messages = (
        Message(role="assistant", content=HOSTILE, tool_calls=(call,)),
        Message(role="tool", content=HOSTILE, tool_call_id="c"),
    )
    out = trajectory_section(Trajectory(messages=messages))
    assert "<script" not in out and out.count("&lt;script&gt;") == 4


def test_case_detail_includes_the_trajectory_of_an_agent_run() -> None:
    output = ModelOutput(text="done", latency_ms=1, trajectory=agent_trajectory())
    out = case_detail(0, CaseResult(case_id="agent", output=output))
    assert "Agent trajectory" in out and "Tool result" in out
    assert "Agent trajectory" not in case_detail(0, full_result())
