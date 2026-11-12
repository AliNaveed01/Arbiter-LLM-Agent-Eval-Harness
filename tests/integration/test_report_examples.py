"""Reports built from the shipped examples, and the committed sample report."""

import re
from pathlib import Path

from typer.testing import CliRunner

from agentgauge.cli import app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner(env={"COLUMNS": "200"})


def assert_self_contained(html: str) -> None:
    assert html.startswith("<!doctype html>")
    assert "<script" not in html.lower()
    assert "default-src &#x27;none&#x27;" in html
    assert not re.search(r"(https?:)?//", html)


def test_the_committed_sample_report_is_self_contained_and_shows_the_regression() -> None:
    html = (ROOT / "docs" / "examples" / "regression-report.html").read_text()
    assert_self_contained(html)
    assert "✗ REGRESSION" in html and "<svg" in html and "Regressed (7)" in html


def test_a_fresh_report_from_the_regression_example(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    for name in ("baseline", "candidate"):
        run = runner.invoke(
            app, ["run", str(ROOT / "examples" / "regression" / f"{name}.yaml"), "--db", str(db)]
        )
        assert run.exit_code == 0, run.output
    target = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["report", "latest", "--baseline", "previous", "--db", str(db), "--output", str(target)],
    )
    assert result.exit_code == 0 and "(regression)" in result.output
    html = target.read_text()
    assert_self_contained(html)
    assert html.count('<details class="case"') == 12
    assert "McNemar p = 0.0156" in html


def test_an_agent_run_report_shows_the_trajectories(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    suite = ROOT / "examples" / "agent" / "suite.yaml"
    assert runner.invoke(app, ["run", str(suite), "--db", str(db)]).exit_code == 0
    target = tmp_path / "agent.html"
    result = runner.invoke(app, ["report", "latest", "--db", str(db), "--output", str(target)])
    assert result.exit_code == 0, result.output
    html = target.read_text()
    assert_self_contained(html)
    assert html.count("Agent trajectory") == 4
    assert "cut off at the step limit" in html  # the never-finishes case
    assert "-&gt; search_flights" in html and "Tool result" in html
