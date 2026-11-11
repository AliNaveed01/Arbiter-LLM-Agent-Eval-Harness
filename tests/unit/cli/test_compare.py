import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.core import CaseResult, RunResult, Score
from agentgauge.storage import RunStore

runner = CliRunner(env={"COLUMNS": "200"})
T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def make_run(
    run_id: str, passes: list[bool], *, minutes: int = 0, suite: str = "demo"
) -> RunResult:
    results = tuple(
        CaseResult(
            case_id=f"c{i}",
            scores=(Score(scorer="exact_match", value=float(ok), passed=ok),),
            latency_ms=5.0,
        )
        for i, ok in enumerate(passes)
    )
    return RunResult(
        run_id=run_id,
        suite_name=suite,
        model="m",
        started_at=T0 + timedelta(minutes=minutes),
        finished_at=T0 + timedelta(minutes=minutes, seconds=1),
        results=results,
    )


def store_runs(tmp_path: Path, *runs: RunResult) -> Path:
    db = tmp_path / "runs.db"
    with RunStore(db) as store:
        for run in runs:
            store.save_run(run)
    return db


GOOD = [True] * 30
BAD = [False] * 10 + [True] * 20


def test_a_significant_regression_exits_1(tmp_path: Path) -> None:
    db = store_runs(tmp_path, make_run("aaaa1111", GOOD), make_run("bbbb2222", BAD, minutes=5))
    result = runner.invoke(app, ["compare", "aaaa", "bbbb", "--db", str(db)])
    assert result.exit_code == 1, result.output
    assert "REGRESSION" in result.output and "Regressed (10)" in result.output


def test_no_significant_change_and_improvements_exit_0(tmp_path: Path) -> None:
    db = store_runs(
        tmp_path,
        make_run("aaaa1111", GOOD),
        make_run("bbbb2222", GOOD, minutes=5),
        make_run("cccc3333", BAD, minutes=1),
    )
    same = runner.invoke(app, ["compare", "aaaa", "bbbb", "--db", str(db)])
    assert same.exit_code == 0 and "No significant change" in same.output
    better = runner.invoke(app, ["compare", "cccc", "aaaa", "--db", str(db)])
    assert better.exit_code == 0 and "Improvement" in better.output


def test_latest_and_previous_pick_runs_by_time(tmp_path: Path) -> None:
    db = store_runs(
        tmp_path,
        make_run("aaaa1111", GOOD, minutes=0),
        make_run("bbbb2222", BAD, minutes=5),
        make_run("zzzz9999", GOOD, minutes=9, suite="other"),
    )
    plain = runner.invoke(app, ["compare", "previous", "latest", "--db", str(db)])
    assert plain.exit_code == 0 and "other" in plain.output  # compared bbbb with zzzz: a gain
    scoped = runner.invoke(
        app,
        ["compare", "previous", "latest", "--suite", "demo", "--db", str(db), "--format", "json"],
    )
    assert scoped.exit_code == 1
    assert json.loads(scoped.output)["baseline_id"] == "aaaa1111"


def test_max_drop_and_alpha_change_the_verdict(tmp_path: Path) -> None:
    db = store_runs(tmp_path, make_run("aaaa1111", GOOD), make_run("bbbb2222", BAD, minutes=5))
    tolerated = runner.invoke(
        app, ["compare", "aaaa", "bbbb", "--db", str(db), "--max-drop", "0.5"]
    )
    assert tolerated.exit_code == 0
    strict = runner.invoke(app, ["compare", "aaaa", "bbbb", "--db", str(db), "--alpha", "0.001"])
    assert strict.exit_code == 0  # p = 0.00195


def test_markdown_and_json_go_to_stdout_or_a_file(tmp_path: Path) -> None:
    db = store_runs(tmp_path, make_run("aaaa1111", GOOD), make_run("bbbb2222", BAD, minutes=5))
    md = runner.invoke(app, ["compare", "aaaa", "bbbb", "--db", str(db), "--format", "markdown"])
    assert md.exit_code == 1 and md.output.startswith("### agentgauge: REGRESSION")
    target = tmp_path / "out" / "summary.md"
    filed = runner.invoke(
        app,
        [
            "compare",
            "aaaa",
            "bbbb",
            "--db",
            str(db),
            "--format",
            "markdown",
            "--output",
            str(target),
        ],
    )
    assert filed.exit_code == 1 and "regression: wrote" in filed.output
    assert target.read_text().startswith("### agentgauge: REGRESSION")
    as_json = runner.invoke(app, ["compare", "aaaa", "bbbb", "--db", str(db), "--format", "json"])
    assert json.loads(as_json.output)["verdict"] == "regression"


def test_configuration_problems_exit_2(tmp_path: Path) -> None:
    db = store_runs(
        tmp_path,
        make_run("aaaa1111", GOOD),
        make_run("bbbb2222", GOOD, minutes=5),
    )
    cases = [
        (["compare", "nope", "aaaa"], "no run matches"),
        (["compare", "aaaa", "bbbb", "--alpha", "2"], "alpha"),
        (["compare", "aaaa", "bbbb", "--output", "x.md"], "--output needs"),
        (["compare", "latest", "latest", "--suite", "missing"], "only 0 stored run"),
    ]
    for args, message in cases:
        result = runner.invoke(app, [*args, "--db", str(db)])
        assert result.exit_code == 2, (args, result.output)
        assert message in result.output


def test_ambiguous_prefix_and_disjoint_runs_exit_2(tmp_path: Path) -> None:
    other = RunResult(
        run_id="eeee5555",
        suite_name="demo",
        model="m",
        started_at=T0,
        results=(CaseResult(case_id="different"),),
    )
    db = store_runs(
        tmp_path, make_run("aaaa1111", GOOD), make_run("aaaa2222", GOOD, minutes=1), other
    )
    ambiguous = runner.invoke(app, ["compare", "aaaa", "eeee", "--db", str(db)])
    assert ambiguous.exit_code == 2 and "ambiguous" in ambiguous.output
    disjoint = runner.invoke(app, ["compare", "aaaa1", "eeee", "--db", str(db)])
    assert disjoint.exit_code == 2 and "share no case ids" in disjoint.output


def test_an_unusable_database_exits_2(tmp_path: Path) -> None:
    broken = tmp_path / "dir-not-file"
    broken.mkdir()
    result = runner.invoke(app, ["compare", "a", "b", "--db", str(broken)])
    assert result.exit_code == 2
