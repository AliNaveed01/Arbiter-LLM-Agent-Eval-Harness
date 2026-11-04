import io
from datetime import UTC, datetime, timedelta

from rich.console import Console

from agentgauge.calibration import CalibrationReport, calibrate
from agentgauge.cli.render import (
    kappa_warning,
    render_calibration,
    render_run,
    render_run_list,
    summarize,
)
from agentgauge.core import CaseResult, ModelOutput, RunResult, Score
from agentgauge.judge import Scale
from agentgauge.storage import RunSummary

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=140, color_system=None, force_terminal=False), buffer


def good(case_id: str, cost: float | None = None) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        output=ModelOutput(text="four", latency_ms=1),
        scores=(Score(scorer="exact_match", value=1.0, passed=True),),
        latency_ms=12.4,
        cost_usd=cost,
    )


def bad(case_id: str) -> CaseResult:
    score = Score(scorer="exact_match", value=0.0, passed=False, reason="expected '4'")
    return CaseResult(
        case_id=case_id,
        output=ModelOutput(text="five " * 30, latency_ms=1),
        scores=(score,),
        latency_ms=8.0,
    )


def broke(case_id: str) -> CaseResult:
    return CaseResult(case_id=case_id, error="TimeoutError: slow", latency_ms=None)


def run(results: tuple[CaseResult, ...], finished: bool = True) -> RunResult:
    return RunResult(
        run_id="0123456789abcdef",
        suite_name="basic",
        model="fake",
        started_at=T0,
        finished_at=T0 + timedelta(seconds=2.5) if finished else None,
        results=results,
    )


def test_summarize_counts_outcomes_cost_and_duration() -> None:
    stats = summarize(run((good("a", 0.001), good("b", 0.002), bad("c"), broke("d"))))
    assert (stats.total, stats.passed, stats.failed, stats.errored) == (4, 2, 1, 1)
    assert stats.cost_usd == 0.003
    assert stats.duration_s == 2.5


def test_summarize_without_cost_or_finish_time() -> None:
    stats = summarize(run((good("a"),), finished=False))
    assert (stats.cost_usd, stats.duration_s) == (None, None)


def test_summarize_empty_run() -> None:
    stats = summarize(run(()))
    assert (stats.total, stats.passed, stats.failed, stats.errored) == (0, 0, 0, 0)


def test_render_run_shows_header_rows_and_summary() -> None:
    con, out = console()
    render_run(con, run((good("add", 0.0012), bad("sub"), broke("mul"))))
    text = out.getvalue()
    assert "Run 01234567  suite basic  model fake  started 2026-11-03 12:00:00 UTC" in text
    assert "add" in text and "PASS" in text and "exact_match=pass" in text
    assert "FAIL" in text and "exact_match: expected '4'" in text
    assert "ERROR" in text and "TimeoutError: slow" in text
    assert "12 ms" in text
    assert "1/3 passed, 1 failed, 1 errors, cost $0.0012, took 2.50s" in text


def test_render_run_handles_missing_latency_scores_and_finish() -> None:
    con, out = console()
    render_run(con, run((broke("x"), CaseResult(case_id="y")), finished=False))
    text = out.getvalue()
    assert "1/2 passed, 0 failed, 1 errors" in text
    assert "took" not in text and "cost" not in text


def test_verbose_adds_an_output_column_with_truncation() -> None:
    con, out = console()
    render_run(con, run((good("a"), bad("b"), broke("c"))), verbose=True)
    text = out.getvalue()
    assert "Output" in text
    assert "four" in text
    assert "five five" in text and "…" in text
    plain, plain_out = console()
    render_run(plain, run((good("a"),)))
    assert "Output" not in plain_out.getvalue()


def test_text_with_brackets_is_not_treated_as_markup() -> None:
    con, out = console()
    tricky = CaseResult(case_id="[bold]id[/bold]", error="bad [/oops] value")
    render_run(con, run((tricky,)))
    assert "[bold]id[/bold]" in out.getvalue()
    assert "bad [/oops] value" in out.getvalue()


def test_render_run_list() -> None:
    con, out = console()
    summary = RunSummary(
        run_id="fedcba9876543210",
        suite_name="basic",
        model="fake",
        started_at=T0,
        finished_at=None,
        total_cases=4,
        passed_cases=3,
        errored_cases=1,
    )
    render_run_list(con, [summary])
    text = out.getvalue()
    assert "fedcba98" in text and "fedcba9876543210" not in text
    assert "2026-11-03 12:00:00 UTC" in text
    assert all(word in text for word in ("Suite", "Model", "Cases", "Passed", "Errors"))


def test_render_empty_run_list() -> None:
    con, out = console()
    render_run_list(con, [])
    assert "No runs stored yet" in out.getvalue()


def _report(human: list[int], judge: list[int], scale: object = "binary") -> CalibrationReport:
    return calibrate(human, judge, Scale.model_validate(scale))


def test_calibration_report_shows_numbers_matrix_and_per_class() -> None:
    con, buffer = console()
    report = _report([1, 1, 0, 0, 1, 0, 1, 1], [1, 1, 0, 0, 1, 0, 1, 0])
    render_calibration(con, report, suite_name="arith", judge_model="judge-1")
    out = buffer.getvalue()
    assert "calibration of arith  judge judge-1" in out
    assert "cases compared" in out and "8" in out
    assert "accuracy" in out and "0.88" in out
    assert "kappa (none weighting)" in out and "95% CI" in out
    assert "Confusion matrix" in out
    assert "precision" in out and "recall" in out
    assert "Warning" not in out


def test_low_kappa_warns_that_the_judge_is_not_trustworthy() -> None:
    con, buffer = console()
    report = _report([1, 0, 1, 0], [0, 1, 1, 0])
    render_calibration(con, report, suite_name="s", judge_model="j")
    out = buffer.getvalue()
    assert "Warning" in out
    assert "below 0.6" in out
    assert "not trustworthy" in " ".join(out.split())


def test_good_agreement_has_no_warning() -> None:
    report = _report([1, 1, 1, 0, 0, 0, 1, 0], [1, 1, 1, 0, 0, 0, 1, 0])
    assert kappa_warning(report) is None


def test_undefined_kappa_is_reported_and_warned() -> None:
    con, buffer = console()
    report = _report([1, 1, 1], [1, 1, 1])
    render_calibration(con, report, suite_name="s", judge_model="j")
    out = buffer.getvalue()
    assert "undefined" in out
    assert "n/a" in out
    assert "cannot show that the judge is trustworthy" in " ".join(out.split())


def test_skipped_and_unlabelled_cases_are_mentioned() -> None:
    con, buffer = console()
    render_calibration(
        con,
        _report([1, 0, 1, 0], [1, 0, 1, 0]),
        suite_name="s",
        judge_model="j",
        skipped=("c9", "c10"),
        unlabelled=3,
    )
    out = buffer.getvalue()
    assert "2 labelled case(s) not compared" in out and "c9, c10" in out
    assert "3 case(s) in the suite have no label" in out


def test_ordinal_report_uses_quadratic_weighting_and_brackets_in_text_are_literal() -> None:
    con, buffer = console()
    render_calibration(
        con, _report([1, 2, 3, 3], [1, 3, 3, 2], 3), suite_name="[x]", judge_model="[bold]j"
    )
    out = buffer.getvalue()
    assert "quadratic weighting" in out
    assert "calibration of [x]  judge [bold]j" in out
