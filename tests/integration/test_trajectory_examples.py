"""The agent and OTel examples must keep working: docs/trajectories.md walks through them."""

import os
import subprocess
import sys
from pathlib import Path

from agentgauge.core import load_suite
from agentgauge.otel import load_traces
from agentgauge.storage import RunStore

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "examples" / "agent" / "suite.yaml"
OTEL_SUITE = ROOT / "examples" / "otel" / "suite.yaml"
OTEL_TRACES = ROOT / "examples" / "otel" / "traces.json"
WIDE = {**os.environ, "COLUMNS": "200"}


def cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentgauge", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
        env=WIDE,
    )


def test_agent_example_loads_with_a_loop_and_mocks() -> None:
    suite = load_suite(AGENT)
    assert suite.agent is not None and suite.agent.max_steps == 4
    assert len(suite.cases) == 4 and len(suite.tools) == 2 and len(suite.tool_mocks) == 2


def test_agent_example_runs_and_one_case_never_finishes(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    result = cli(tmp_path, "run", str(AGENT), "--db", str(db))
    assert result.returncode == 0, result.stderr
    assert "3/4 passed, 1 failed, 0 errors" in result.stdout
    with RunStore(db) as store:
        run = store.get_run(store.list_runs()[0].run_id)
    outcomes = {r.case_id: r.passed for r in run.results}
    assert outcomes == {
        "book-cheapest": True,
        "no-tool-needed": True,
        "search-twice": True,
        "never-finishes": False,
    }
    stuck = next(r for r in run.results if r.case_id == "never-finishes")
    assert stuck.output is not None and stuck.output.trajectory is not None
    assert stuck.output.trajectory.stop_reason == "max_steps"
    assert stuck.output.trajectory.steps == 4


def test_agent_example_trajectory_can_be_shown(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    cli(tmp_path, "run", str(AGENT), "--db", str(db))
    with RunStore(db) as store:
        run_id = store.list_runs()[0].run_id
    shown = cli(tmp_path, "runs", "show", run_id[:8], "--trajectory", "--db", str(db))
    assert shown.returncode == 0, shown.stderr
    out = shown.stdout
    assert "book-cheapest  3 step(s), 2 tool call(s), stopped: final" in out
    assert "never-finishes  4 step(s), 4 tool call(s), stopped: max_steps" in out
    assert "result     Confirmed: FL100" in out


def test_otel_example_files_are_consistent() -> None:
    traces, skipped = load_traces(OTEL_TRACES)
    assert sorted(t.case_id or "" for t in traces) == ["book-cheapest", "refund-flow"]
    assert skipped == 1
    assert {c.id for c in load_suite(OTEL_SUITE).cases} == {"book-cheapest", "refund-flow"}


def test_otel_example_imports_and_scores(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    result = cli(
        tmp_path, "import-otel", str(OTEL_TRACES), "--suite", str(OTEL_SUITE), "--db", str(db)
    )
    assert result.returncode == 0, result.stderr
    assert "1/2 passed, 1 failed, 0 errors" in result.stdout
    assert "Imported 2 trace(s)" in result.stdout
    assert "1 trace(s) without GenAI spans were ignored" in " ".join(result.stdout.split())
    with RunStore(db) as store:
        run = store.get_run(store.list_runs()[0].run_id)
    assert run.model == "gpt-demo"
    first = next(r for r in run.results if r.case_id == "book-cheapest")
    assert first.output is not None and first.output.prompt_tokens == 120
    assert first.output.text == "Booked FL100 for $200."
