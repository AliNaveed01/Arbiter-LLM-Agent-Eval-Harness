"""The shipped example must keep working: it is what the README quickstart runs."""

import os
import subprocess
import sys
from pathlib import Path

from agentgauge.core import load_suite
from agentgauge.storage import RunStore

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "examples" / "basic" / "suite.yaml"
WIDE = {**os.environ, "COLUMNS": "200"}  # keep Rich tables from wrapping cells


def test_example_suite_loads_and_is_self_contained() -> None:
    suite = load_suite(SUITE)
    assert suite.provider is not None and suite.provider.type == "fake"
    assert len(suite.cases) == 4


def test_example_runs_through_the_installed_cli(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    command = [sys.executable, "-m", "agentgauge", "run", str(SUITE), "--db", str(db)]
    result = subprocess.run(
        command, capture_output=True, text=True, cwd=tmp_path, check=False, env=WIDE
    )
    assert result.returncode == 0, result.stderr
    assert "3/4 passed, 1 failed, 0 errors" in result.stdout
    with RunStore(db) as store:
        (summary,) = store.list_runs()
        assert (summary.suite_name, summary.total_cases, summary.passed_cases) == ("basic", 4, 3)


def test_example_run_can_be_listed_and_shown(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    base = [sys.executable, "-m", "agentgauge"]
    subprocess.run([*base, "run", str(SUITE), "--db", str(db)], capture_output=True, check=True)
    listing = subprocess.run(
        [*base, "runs", "list", "--db", str(db)],
        capture_output=True,
        text=True,
        check=True,
        env=WIDE,
    )
    assert "basic" in listing.stdout and "scripted-demo" in listing.stdout
    with RunStore(db) as store:
        run_id = store.list_runs()[0].run_id
    shown = subprocess.run(
        [*base, "runs", "show", run_id[:8], "--db", str(db)],
        capture_output=True,
        text=True,
        check=True,
        env=WIDE,
    )
    assert "capital-australia" in shown.stdout and "Sydney" in shown.stdout
