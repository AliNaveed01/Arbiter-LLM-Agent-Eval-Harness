from datetime import UTC, datetime, timedelta

from agentgauge.core.models import CaseResult, ModelOutput, RunResult, Score
from agentgauge.report.case import case_status
from agentgauge.report.run import (
    cases_table,
    duration,
    moment,
    render_run_report,
    run_summary,
)

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def result(case_id: str, passed: bool = True, **kwargs: object) -> CaseResult:
    score = Score(scorer="exact_match", value=float(passed), passed=passed)
    return CaseResult(case_id=case_id, scores=(score,), **kwargs)  # type: ignore[arg-type]


def make_run(*results: CaseResult, finished: bool = True, suite: str = "demo") -> RunResult:
    return RunResult(
        run_id="abcdef0123456789",
        suite_name=suite,
        model="model-x",
        started_at=T0,
        finished_at=T0 + timedelta(seconds=2.5) if finished else None,
        results=results,
    )


def test_summary_counts_outcomes_and_names_the_run() -> None:
    run = make_run(
        result("a", latency_ms=10.0, cost_usd=0.001),
        result("b", passed=False, latency_ms=30.0, cost_usd=0.002),
        CaseResult(case_id="c", error="timeout"),
    )
    out = run_summary(run)
    assert "<h1>Run report: demo</h1>" in out
    assert "model model-x, run abcdef01, started 2026-11-03 12:00:00 UTC, took 2.50 s" in out
    for value, label in [("3", "cases"), ("1", "passed"), ("1", "failed"), ("1", "errors")]:
        assert f"<li><b>{value}</b>{label}</li>" in out
    assert "<li><b>33%</b>pass rate</li>" in out
    assert "<li><b>20 ms</b>mean latency</li>" in out
    assert "<li><b>$0.0030</b>cost</li>" in out


def test_summary_omits_what_is_unknown() -> None:
    out = run_summary(make_run(result("a"), finished=False))
    assert "took" not in out and "mean latency" not in out and "cost" not in out


def test_a_zero_cost_is_not_shown_as_a_cost() -> None:
    out = run_summary(make_run(result("a", cost_usd=0.0), result("b", cost_usd=0.0)))
    assert "cost" not in out


def test_an_empty_run_has_no_pass_rate() -> None:
    assert "<li><b>n/a</b>pass rate</li>" in run_summary(make_run())


def test_summary_escapes_the_suite_and_model_names() -> None:
    run = make_run(suite="<img src=x onerror=alert(1)>").model_copy(update={"model": "</p><b>"})
    out = run_summary(run)
    assert "<img" not in out and "</p><b>" not in out
    assert "&lt;img src=x onerror=alert(1)&gt;" in out and "model &lt;/p&gt;&lt;b&gt;" in out


def test_moment_and_duration() -> None:
    assert moment(T0) == "2026-11-03 12:00:00 UTC"
    assert duration(make_run(finished=False)) is None
    assert duration(make_run()) == "2.50 s"


def test_status_uses_an_icon_and_a_word_as_well_as_a_class() -> None:
    assert case_status(result("a")) == ("pass", "✓", "pass")
    assert case_status(result("a", passed=False)) == ("fail", "✗", "fail")
    assert case_status(
        CaseResult(case_id="a", error="x", output=ModelOutput(text="", latency_ms=0))
    ) == (
        "error",
        "!",
        "error",
    )


def table_run() -> RunResult:
    bad = Score(scorer="contains", value=0.0, passed=False, reason="missing 'Paris'")
    return make_run(
        result("ok-case", latency_ms=12.4),
        CaseResult(case_id="bad-case", scores=(bad,), latency_ms=80.0),
        CaseResult(case_id="err-case", error="HTTP 500: boom"),
    )


def test_the_table_has_one_row_per_case_with_status_scores_latency_and_reason() -> None:
    out = cases_table(table_run())
    assert out.count("<tr>") == 4  # header plus three cases
    assert '<td class="status pass">✓ pass</td>' in out
    assert '<td class="status fail">✗ fail</td>' in out
    assert '<td class="status error">! error</td>' in out
    assert "<td>exact_match 1</td>" in out and "<td>contains 0</td>" in out
    assert '<td class="num">12 ms</td>' in out and '<td class="num">-</td>' in out
    assert "<td>contains: missing &#x27;Paris&#x27;</td>" in out
    assert "<td>HTTP 500: boom</td>" in out
    assert out.startswith('<div class="scroll"><table>')


def test_a_failing_score_without_a_reason_still_names_the_scorer() -> None:
    bad = Score(scorer="regex", value=0.0, passed=False)
    out = cases_table(make_run(CaseResult(case_id="a", scores=(bad,))))
    assert "<td>regex</td>" in out


def test_the_table_escapes_case_ids_scorers_and_errors() -> None:
    hostile = "<script>alert(1)</script>"
    run = make_run(
        CaseResult(case_id=hostile, error=hostile),
        CaseResult(case_id="b", scores=(Score(scorer=hostile, value=0, passed=False),)),
    )
    out = cases_table(run)
    assert "<script" not in out and out.count("&lt;script&gt;") == 4


def test_an_empty_run_has_no_table() -> None:
    assert cases_table(make_run()) == '<p class="muted">No cases.</p>'


def test_the_report_page_combines_summary_and_table() -> None:
    page_text = render_run_report(table_run(), theme="dark")
    assert page_text.startswith("<!doctype html>") and 'data-theme="dark"' in page_text
    assert "<title>agentgauge run demo</title>" in page_text
    assert page_text.index("<h1>") < page_text.index("<h2>Cases</h2>") < page_text.index("<table>")
