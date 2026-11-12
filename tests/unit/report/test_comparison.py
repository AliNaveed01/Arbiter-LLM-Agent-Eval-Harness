from datetime import UTC, datetime

from agentgauge.compare import compare_runs, to_markdown
from agentgauge.core.models import CaseResult, RunResult, Score
from agentgauge.report.comparison import comparison_section
from agentgauge.report.run import render_run_report


def case(case_id: str, ok: bool, latency: float | None = None) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        scores=(Score(scorer="exact_match", value=float(ok), passed=ok),),
        latency_ms=latency,
    )


def run(results: list[CaseResult], run_id: str, suite: str = "demo") -> RunResult:
    return RunResult(
        run_id=run_id,
        suite_name=suite,
        model="model-" + run_id,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=tuple(results),
    )


def pair(total: int, regress: int, improve: int = 0) -> tuple[RunResult, RunResult]:
    base, cand = [], []
    for i in range(total):
        before, after = (
            (True, False)
            if i < regress
            else (False, True)
            if i < regress + improve
            else (True, True)
        )
        base.append(case(f"c{i}", before, 10.0))
        cand.append(case(f"c{i}", after, 25.0))
    return run(base, "baseline1"), run(cand, "candidate")


def test_a_regression_is_stated_with_icon_word_and_numbers() -> None:
    out = comparison_section(compare_runs(*pair(30, 10)))
    assert '<span class="status fail">✗ REGRESSION</span>' in out
    assert "Pass rate fell from 100.0% to 66.7%" in out
    assert "<td>-33.3 points (" in out
    assert '<td class="num">100.0%</td><td class="num">66.7%</td>' in out
    assert "<td><code>exact_match</code> mean score</td>" in out
    assert '<td class="num">10 ms</td><td class="num">25 ms</td><td>+15 ms</td>' in out
    assert "<b>Regressed (10): </b>" in out and "Improved" not in out


def test_improvement_and_no_change_use_their_own_icon_and_class() -> None:
    better = comparison_section(compare_runs(*reversed(pair(30, 10))))
    assert '<span class="status pass">✓ Improvement</span>' in better
    same = comparison_section(compare_runs(*pair(10, 0)))
    assert '<span class="status muted">= No significant change</span>' in same


def test_the_report_states_the_same_numbers_as_the_markdown() -> None:
    comparison = compare_runs(*pair(30, 10), seed=3)
    out = comparison_section(comparison)
    markdown = to_markdown(comparison)
    for fragment in ("100.0%", "66.7%", "-33.3 points", "p = 0.00195"):
        assert fragment in out and fragment in markdown


def test_case_ids_link_to_their_detail_and_are_escaped() -> None:
    base = run([case("<b>x</b>", True), case("plain", True)], "b")
    cand = run([case("<b>x</b>", False), case("plain", False)], "c")
    comparison = compare_runs(base, cand)
    out = comparison_section(comparison, {"<b>x</b>": 0, "plain": 1})
    assert '<a href="#case-0"><code>&lt;b&gt;x&lt;/b&gt;</code></a>' in out
    assert "<b>x</b>" not in out
    unlinked = comparison_section(comparison)
    assert "<a " not in unlinked


def test_long_lists_are_cut_and_notes_are_shown() -> None:
    base = run([case(f"c{i}", True) for i in range(30)] + [case("old", True)], "b", suite="a")
    cand = run([case(f"c{i}", False) for i in range(30)], "c", suite="b")
    out = comparison_section(compare_runs(base, cand))
    assert "and 10 more" in out
    assert "Note: the runs are of different suites" in out
    assert "Note: 1 case(s) only in the baseline were left out" in out


def test_the_run_report_places_the_comparison_between_summary_and_cases() -> None:
    base, cand = pair(30, 10)
    page_text = render_run_report(cand, comparison=compare_runs(base, cand))
    assert (
        page_text.index("<h1>")
        < page_text.index("<h2>Comparison</h2>")
        < page_text.index("<h2>Cases</h2>")
    )
    assert 'href="#case-0"' in page_text and 'id="case-0"' in page_text
    assert "<h2>Comparison</h2>" not in render_run_report(cand)
