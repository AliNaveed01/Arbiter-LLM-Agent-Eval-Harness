from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.core import CaseResult, ModelOutput, RunResult, Score
from agentgauge.storage import RunStore

runner = CliRunner(env={"COLUMNS": "200"})
T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def make_run(run_id: str, minutes: int = 0, suite: str = "demo") -> RunResult:
    return RunResult(
        run_id=run_id,
        suite_name=suite,
        model="m",
        started_at=T0 + timedelta(minutes=minutes),
        results=(
            CaseResult(
                case_id="a<b",
                output=ModelOutput(text="<script>alert(1)</script>", latency_ms=3),
                scores=(Score(scorer="exact_match", value=0, passed=False, reason="differs"),),
            ),
        ),
    )


def stored(tmp_path: Path, *runs: RunResult) -> Path:
    db = tmp_path / "runs.db"
    with RunStore(db) as store:
        for run in runs:
            store.save_run(run)
    return db


def test_report_writes_a_file_and_prints_its_path(tmp_path: Path) -> None:
    db = stored(tmp_path, make_run("aaaa1111"))
    target = tmp_path / "out" / "r.html"
    result = runner.invoke(app, ["report", "aaaa", "--db", str(db), "--output", str(target)])
    assert result.exit_code == 0, result.output
    assert f"wrote {target}" in result.output
    html = target.read_text()
    assert html.startswith("<!doctype html>") and "Run report: demo" in html
    assert "<script" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_the_default_file_name_comes_from_the_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = stored(tmp_path, make_run("abcdef0123"))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["report", "abcdef", "--db", str(db)])
    assert result.exit_code == 0 and (tmp_path / "agentgauge-report-abcdef01.html").exists()


def test_latest_previous_and_suite_pick_runs(tmp_path: Path) -> None:
    db = stored(
        tmp_path,
        make_run("aaaa1111", 0),
        make_run("bbbb2222", 5, suite="other"),
    )
    target = tmp_path / "r.html"
    latest = runner.invoke(app, ["report", "latest", "--db", str(db), "--output", str(target)])
    assert latest.exit_code == 0 and "Run report: other" in target.read_text()
    scoped = runner.invoke(
        app, ["report", "latest", "--suite", "demo", "--db", str(db), "--output", str(target)]
    )
    assert scoped.exit_code == 0 and "Run report: demo" in target.read_text()


def test_theme_and_expand_reach_the_page(tmp_path: Path) -> None:
    db = stored(tmp_path, make_run("aaaa1111"))
    target = tmp_path / "r.html"
    args = [
        "report",
        "aaaa",
        "--db",
        str(db),
        "--output",
        str(target),
        "--theme",
        "dark",
        "--expand",
    ]
    assert runner.invoke(app, args).exit_code == 0
    html = target.read_text()
    assert 'data-theme="dark"' in html and '<details class="case" id="case-0" open>' in html


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["report", "nope"], "no run matches"),
        (["report", "latest", "--suite", "missing"], "only 0 stored run"),
        (["report", "aaaa", "--theme", "sepia"], "sepia"),
    ],
)
def test_problems_exit_2(tmp_path: Path, args: list[str], message: str) -> None:
    db = stored(tmp_path, make_run("aaaa1111"))
    result = runner.invoke(app, [*args, "--db", str(db)])
    assert result.exit_code == 2 and message in result.output


def test_an_ambiguous_prefix_and_a_broken_database_exit_2(tmp_path: Path) -> None:
    db = stored(tmp_path, make_run("aaaa1111"), make_run("aaaa2222", 1))
    assert "ambiguous" in runner.invoke(app, ["report", "aaaa", "--db", str(db)]).output
    broken = tmp_path / "dir"
    broken.mkdir()
    assert runner.invoke(app, ["report", "a", "--db", str(broken)]).exit_code == 2
