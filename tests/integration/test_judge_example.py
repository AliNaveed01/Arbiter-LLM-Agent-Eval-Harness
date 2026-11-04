"""The judge example must keep working: the calibration docs walk through it."""

import os
import subprocess
import sys
from pathlib import Path

from agentgauge.calibration import load_labels
from agentgauge.core import load_suite

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "examples" / "judge" / "suite.yaml"
LABELS = ROOT / "examples" / "judge" / "labels.yaml"
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


def test_suite_and_labels_agree_on_the_cases() -> None:
    suite = load_suite(SUITE)
    labels = load_labels(LABELS)
    assert [case.id for case in suite.cases] == [label.case_id for label in labels]
    assert suite.provider is not None and suite.provider.type == "fake"


def test_run_scores_cases_with_the_scripted_judge(tmp_path: Path) -> None:
    result = cli(tmp_path, "run", str(SUITE), "--db", str(tmp_path / "runs.db"))
    assert result.returncode == 0, result.stderr
    assert "8/12 passed, 4 failed, 0 errors" in result.stdout
    assert "llm_judge=pass" in result.stdout


def test_calibrate_reports_the_documented_numbers(tmp_path: Path) -> None:
    result = cli(tmp_path, "calibrate", str(SUITE), "--labels", str(LABELS))
    assert result.returncode == 0, result.stderr
    out = " ".join(result.stdout.split())
    assert "calibration of judge-demo judge scripted-judge" in out
    assert "cases compared 12" in out
    assert "accuracy 0.83" in out
    assert "kappa (none weighting) 0.62" in out
    assert "Warning" not in out


def test_calibrating_again_is_served_from_the_judge_cache(tmp_path: Path) -> None:
    first = cli(tmp_path, "calibrate", str(SUITE), "--labels", str(LABELS))
    second = cli(tmp_path, "calibrate", str(SUITE), "--labels", str(LABELS))
    assert first.stdout == second.stdout
    assert (tmp_path / ".agentgauge" / "judge-cache.db").is_file()
