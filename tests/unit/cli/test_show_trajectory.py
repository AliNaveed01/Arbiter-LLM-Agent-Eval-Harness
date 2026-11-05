import io
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.cli.render import render_trajectories
from agentgauge.core import CaseResult, Message, ModelOutput, RunResult, ToolCall, Trajectory
from agentgauge.storage import RunStore

runner = CliRunner(env={"COLUMNS": "200"})

AGENT_SUITE = """\
name: weather-agent
provider:
  type: fake
  model: scripted-agent
  responses:
    "What is the weather in Paris?":
      - tool_calls: [{name: get_weather, arguments: {city: Paris}}]
      - "It is sunny and 21C in Paris."
    "Say hello.": "Hello!"
tools:
  - name: get_weather
    description: Current weather for a city.
    parameters: {type: object, properties: {city: {type: string}}}
tool_mocks:
  - {tool: get_weather, arguments: {city: Paris}, result: "sunny, 21C"}
agent: {max_steps: 4}
scorers:
  - name: trajectory_match
    params: {mode: exact}
cases:
  - id: weather
    input: "What is the weather in Paris?"
    metadata:
      expected_trajectory: [{name: get_weather, arguments: {city: Paris}}]
  - id: greeting
    input: "Say hello."
    metadata: {expected_trajectory: []}
"""


def run_agent_suite(tmp_path: Path) -> str:
    suite = tmp_path / "suite.yaml"
    suite.write_text(AGENT_SUITE)
    db = tmp_path / "runs.db"
    result = runner.invoke(app, ["run", str(suite), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "2/2 passed" in result.output
    with RunStore(db) as store:
        return store.list_runs()[0].run_id


def test_run_stores_trajectories_and_show_trajectory_prints_every_step(tmp_path: Path) -> None:
    run_id = run_agent_suite(tmp_path)
    result = runner.invoke(
        app, ["runs", "show", run_id[:8], "--trajectory", "--db", str(tmp_path / "runs.db")]
    )
    out = result.output
    assert result.exit_code == 0, out
    assert "Trajectories" in out
    assert "weather  2 step(s), 1 tool call(s), stopped: final" in out
    assert 'call       get_weather {"city": "Paris"}' in out
    assert "result     sunny, 21C" in out
    assert "assistant  It is sunny and 21C in Paris." in out
    assert "greeting  1 step(s), 0 tool call(s), stopped: final" in out


def test_show_without_the_flag_has_no_trajectory_section(tmp_path: Path) -> None:
    run_id = run_agent_suite(tmp_path)
    result = runner.invoke(app, ["runs", "show", run_id, "--db", str(tmp_path / "runs.db")])
    assert result.exit_code == 0
    assert "Trajectories" not in result.output


def test_cases_without_a_trajectory_say_so_and_odd_steps_render() -> None:
    call = ToolCall(id="1", name="search", arguments='{"q": "' + "x" * 200 + '"}')
    cut_off = Trajectory(
        messages=(
            Message(role="assistant", content="Let me look.", tool_calls=(call,)),
            Message(role="tool", content="line one\nline two", tool_call_id="1"),
            Message(role="assistant", content=""),
        ),
        stop_reason="max_steps",
    )
    run = RunResult(
        run_id="r1",
        suite_name="s",
        model="m",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=(
            CaseResult(case_id="plain", output=ModelOutput(text="x", latency_ms=1.0)),
            CaseResult(case_id="failed", error="boom"),
            CaseResult(
                case_id="long", output=ModelOutput(text="", latency_ms=1.0, trajectory=cut_off)
            ),
        ),
    )
    buffer = io.StringIO()
    render_trajectories(Console(file=buffer, width=140, color_system=None), run)
    out = buffer.getvalue()
    assert "plain: no trajectory recorded" in out and "failed: no trajectory recorded" in out
    assert "long  2 step(s), 1 tool call(s), stopped: max_steps" in out
    assert "assistant  Let me look." in out
    assert "result     line one line two" in out
    assert "(empty reply)" in out
    assert "…" in out
