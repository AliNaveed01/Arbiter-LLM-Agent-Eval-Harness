"""The GitHub Action: its file is valid, uses real CLI options, and its step behaves."""

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.core import CaseResult, RunResult, Score
from agentgauge.storage import RunStore

ROOT = Path(__file__).resolve().parents[2]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
EXAMPLE = yaml.safe_load((ROOT / "examples" / "github-action" / "regression.yml").read_text())


def compare_step() -> dict[str, Any]:
    (step,) = [s for s in ACTION["runs"]["steps"] if s.get("id") == "compare"]
    return step


def test_action_is_a_composite_action_with_documented_inputs() -> None:
    assert ACTION["runs"]["using"] == "composite"
    inputs = ACTION["inputs"]
    assert inputs["baseline"]["required"] and inputs["candidate"]["required"]
    assert {"db", "suite", "alpha", "max-drop", "resamples", "seed", "version"} <= set(inputs)
    assert all("description" in spec for spec in inputs.values())
    assert ACTION["outputs"]["exit-code"]["value"].endswith("steps.compare.outputs.exit-code }}")


def test_inputs_reach_the_script_through_environment_variables_not_interpolation() -> None:
    step = compare_step()
    assert "${{" not in step["run"], "inputs must not be interpolated into the script"
    assert set(step["env"]) >= {"BASELINE", "CANDIDATE", "DB", "ALPHA", "MAX_DROP"}


def test_every_option_the_action_passes_exists_on_the_command() -> None:
    options = set(re.findall(r"(--[a-z][a-z-]*)", compare_step()["run"]))
    assert {"--db", "--alpha", "--max-drop", "--format", "--output", "--suite"} <= options
    help_text = CliRunner(env={"COLUMNS": "200"}).invoke(app, ["compare", "--help"]).output
    for option in options:
        assert option in help_text, option


def test_example_workflow_runs_both_branches_then_the_action() -> None:
    steps = EXAMPLE["jobs"]["compare"]["steps"]
    assert [s.get("with", {}).get("ref") for s in steps[:1]] == ["${{ github.base_ref }}"]
    action = steps[-1]
    assert action["uses"].startswith("AliNaveed01/agentgauge@")
    assert action["with"]["baseline"] == "previous" and action["with"]["candidate"] == "latest"
    assert sum("agentgauge run" in s.get("run", "") for s in steps) == 2


def run_step(tmp_path: Path, db: Path, **overrides: str) -> tuple[int, str, str, str]:
    """Run the action's compare script under bash against ``db``."""
    script = tmp_path / "step.sh"
    script.write_text(compare_step()["run"])
    summary, output = tmp_path / "summary.md", tmp_path / "output.txt"
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_OUTPUT": str(output),
        "BASELINE": "previous",
        "CANDIDATE": "latest",
        "DB": str(db),
        "SUITE": "",
        "ALPHA": "0.05",
        "MAX_DROP": "0",
        "RESAMPLES": "200",
        "SEED": "0",
        **overrides,
    }
    done = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False
    )
    return (
        done.returncode,
        done.stdout + done.stderr,
        summary.read_text() if summary.exists() else "",
        output.read_text() if output.exists() else "",
    )


def store(tmp_path: Path, second: list[bool]) -> Path:
    db = tmp_path / "runs.db"
    with RunStore(db) as runs:
        for run_id, passes, minute in (("aaaa1111", [True] * 30, 0), ("bbbb2222", second, 5)):
            runs.save_run(
                RunResult(
                    run_id=run_id,
                    suite_name="demo",
                    model="m",
                    started_at=datetime(2026, 11, 3, 12, minute, tzinfo=UTC),
                    results=tuple(
                        CaseResult(
                            case_id=f"c{i}",
                            scores=(Score(scorer="s", value=float(ok), passed=ok),),
                        )
                        for i, ok in enumerate(passes)
                    ),
                )
            )
    return db


def test_the_step_fails_the_job_only_on_a_significant_regression(tmp_path: Path) -> None:
    db = store(tmp_path, [False] * 10 + [True] * 20)
    code, log, summary, output = run_step(tmp_path, db)
    assert code == 1
    assert "::error title=agentgauge::significant regression" in log
    assert summary.startswith("### agentgauge: REGRESSION")
    assert "exit-code=1" in output


def test_the_step_passes_when_the_drop_is_within_max_drop(tmp_path: Path) -> None:
    db = store(tmp_path, [False] * 10 + [True] * 20)
    code, _, summary, output = run_step(tmp_path, db, MAX_DROP="0.5")
    assert code == 0 and "exit-code=0" in output
    assert "No significant change" in summary


def test_the_step_passes_when_nothing_changed(tmp_path: Path) -> None:
    code, _, summary, _ = run_step(tmp_path, store(tmp_path, [True] * 30))
    assert code == 0 and "No significant change" in summary


def test_a_setup_problem_is_reported_as_such_and_not_as_a_regression(tmp_path: Path) -> None:
    db = store(tmp_path, [True] * 30)
    code, log, summary, output = run_step(tmp_path, db, BASELINE="no-such-run")
    assert code == 2 and summary == ""
    assert "could not be compared (exit 2)" in log and "exit-code=2" in output
