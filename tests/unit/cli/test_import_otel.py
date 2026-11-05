import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.storage import RunStore

runner = CliRunner(env={"COLUMNS": "200"})

SUITE = """\
name: otel-agent
scorers:
  - name: trajectory_match
    params: {mode: in_order}
cases:
  - id: weather
    input: "weather in Paris?"
    metadata:
      expected_trajectory: [{name: get_weather, arguments: {city: Paris}}]
  - id: untraced
    input: "never traced"
    metadata: {expected_trajectory: []}
"""


def attr(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "value": {"stringValue": value}}


def span(span_id: str, start: int, operation: str, *attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "traceId": "t1",
        "spanId": span_id,
        "name": operation,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + 1_000_000),
        "attributes": [attr("gen_ai.operation.name", operation), *attrs],
    }


def traces(city: str = "Paris", case_id: str = "weather") -> dict[str, Any]:
    spans = [
        span(
            "a",
            10,
            "chat",
            attr("agentgauge.case_id", case_id),
            attr("gen_ai.response.model", "m-1"),
        ),
        span(
            "b",
            20,
            "execute_tool",
            attr("gen_ai.tool.name", "get_weather"),
            attr("gen_ai.tool.call.arguments", json.dumps({"city": city})),
            attr("gen_ai.tool.call.result", "sunny"),
        ),
        span("c", 30, "chat"),
        span("other", 5, "http"),
    ]
    spans[3]["traceId"] = "unrelated"
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def run_import(tmp_path: Path, trace_doc: Any, *extra: str) -> tuple[int, str]:
    (tmp_path / "suite.yaml").write_text(SUITE)
    (tmp_path / "traces.json").write_text(
        trace_doc if isinstance(trace_doc, str) else json.dumps(trace_doc)
    )
    result = runner.invoke(
        app,
        [
            "import-otel",
            str(tmp_path / "traces.json"),
            "--suite",
            str(tmp_path / "suite.yaml"),
            "--db",
            str(tmp_path / "runs.db"),
            *extra,
        ],
    )
    return result.exit_code, " ".join(result.output.split())


def test_traces_are_imported_scored_and_stored(tmp_path: Path) -> None:
    code, out = run_import(tmp_path, traces())
    assert code == 0, out
    assert "│ weather │ PASS │ trajectory_match=pass" in out
    assert "1/1 passed" in out
    assert "Imported 1 trace(s) as run" in out
    assert "1 trace(s) without GenAI spans were ignored" in out
    assert "1 suite case(s) had no trace" in out
    with RunStore(tmp_path / "runs.db") as store:
        (summary,) = store.list_runs()
        run = store.get_run(summary.run_id)
    assert (run.suite_name, run.model) == ("otel-agent", "m-1")
    assert run.results[0].output is not None and run.results[0].output.trajectory is not None


def test_a_failing_trajectory_is_reported_not_an_error(tmp_path: Path) -> None:
    code, out = run_import(tmp_path, traces(city="Rome"))
    assert code == 0
    assert "│ weather │ FAIL │" in out and "0/1 passed" in out


def test_imported_runs_can_be_shown_with_their_trajectory(tmp_path: Path) -> None:
    run_import(tmp_path, traces())
    with RunStore(tmp_path / "runs.db") as store:
        run_id = store.list_runs()[0].run_id
    shown = runner.invoke(
        app, ["runs", "show", run_id[:8], "--trajectory", "--db", str(tmp_path / "runs.db")]
    )
    assert shown.exit_code == 0
    assert 'call       get_weather {"city": "Paris"}' in shown.output
    assert "result     sunny" in shown.output


def test_configuration_problems_exit_two(tmp_path: Path) -> None:
    for document, message in [
        ("{broken", "invalid JSON"),
        ({"nothing": 1}, "no 'resourceSpans'"),
        (traces(case_id="ghost"), "not in the suite"),
    ]:
        code, out = run_import(tmp_path, document)
        assert code == 2 and message in out


def test_missing_suite_and_bad_trace_file_extension(tmp_path: Path) -> None:
    (tmp_path / "t.txt").write_text("x")
    result = runner.invoke(app, ["import-otel", str(tmp_path / "t.txt"), "--suite", "nope.yaml"])
    assert result.exit_code == 2 and "cannot read file" in result.output
    (tmp_path / "suite.yaml").write_text(SUITE)
    result = runner.invoke(
        app, ["import-otel", str(tmp_path / "t.txt"), "--suite", str(tmp_path / "suite.yaml")]
    )
    assert result.exit_code == 2 and "unsupported file type" in result.output


def test_unusable_database_exits_two(tmp_path: Path) -> None:
    code, out = run_import(tmp_path, traces(), "--db", str(tmp_path))
    assert code == 2 and "cannot open run store" in out


def test_a_misconfigured_scorer_exits_two(tmp_path: Path) -> None:
    (tmp_path / "suite.yaml").write_text(SUITE.replace("trajectory_match", "no_such_scorer"))
    (tmp_path / "traces.json").write_text(json.dumps(traces()))
    result = runner.invoke(
        app,
        [
            "import-otel",
            str(tmp_path / "traces.json"),
            "--suite",
            str(tmp_path / "suite.yaml"),
            "--db",
            str(tmp_path / "runs.db"),
        ],
    )
    assert result.exit_code == 2 and "unknown scorer" in result.output
