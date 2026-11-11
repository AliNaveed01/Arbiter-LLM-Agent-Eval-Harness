import json
from datetime import UTC, datetime

from agentgauge.compare import compare_runs, to_json, to_markdown
from agentgauge.compare.format import latency_change
from agentgauge.core.models import CaseResult, RunResult, Score


def case(case_id: str, passed: bool, latency: float | None = None) -> CaseResult:
    score = Score(scorer="exact_match", value=float(passed), passed=passed)
    return CaseResult(case_id=case_id, scores=(score,), latency_ms=latency)


def run(results: list[CaseResult], run_id: str, suite: str = "demo") -> RunResult:
    return RunResult(
        run_id=run_id,
        suite_name=suite,
        model="model-" + run_id,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=tuple(results),
    )


def regression(total: int = 30, regress: int = 10) -> RunResult:
    return run([case(f"c{i}", i >= regress, latency=20.0) for i in range(total)], "candidate-id-1")


def baseline(total: int = 30) -> RunResult:
    return run([case(f"c{i}", True, latency=10.0) for i in range(total)], "baseline-id-0")


def test_markdown_states_the_verdict_numbers_and_rule() -> None:
    text = to_markdown(compare_runs(baseline(), regression()))
    assert text.startswith("### agentgauge: REGRESSION\n")
    assert "Suite `demo`: baseline `baseline` (`model-baseline-id-0`)" in text
    assert "Pass rate fell from 100.0% to 66.7% (-33.3 points" in text
    assert "exact McNemar p = 0.00195" in text
    assert "| Pass rate | 100.0% | 66.7% | -33.3 points (" in text
    assert "| `exact_match` mean score | 1.000 | 0.667 | -0.333 (-0.500 to -0.167) |" in text
    assert "| Mean latency | 10 ms | 20 ms | +10 ms |" in text
    assert "**Regressed (10):** `c0`, `c1`" in text
    assert "_A regression needs p < 0.05 and a drop of more than 0 points in pass rate._" in text
    assert text.endswith("\n") and "Improved" not in text


def test_markdown_for_an_improvement_and_for_no_change() -> None:
    better = to_markdown(compare_runs(regression(), baseline()))
    assert better.startswith("### agentgauge: Improvement") and "Pass rate rose from" in better
    assert "**Improved (10):**" in better
    same = to_markdown(compare_runs(baseline(), baseline()))
    assert "### agentgauge: No significant change" in same
    assert "Pass rate did not change (100.0%)" in same


def test_long_case_lists_are_cut_and_unshared_cases_are_noted() -> None:
    base = run([case(f"c{i}", True) for i in range(40)] + [case("old", True)], "b")
    cand = run([case(f"c{i}", False) for i in range(40)] + [case("new", True)], "c")
    text = to_markdown(compare_runs(base, cand))
    assert "**Regressed (40):**" in text and "and 20 more" in text
    assert "`c19`" in text and "`c20`" not in text
    assert "1 case(s) only in the baseline were left out" in text
    assert "1 case(s) only in the candidate were left out" in text


def test_backticks_and_markup_in_ids_cannot_break_the_report() -> None:
    base = run([case("a`b", True), case("[x]", True)], "b")
    cand = run([case("a`b", False), case("[x]", False)], "c")
    text = to_markdown(compare_runs(base, cand))
    assert "`a'b`" in text and "`[x]`" in text


def test_warnings_are_listed() -> None:
    other = run([case("c0", True)], "x", suite="other-suite")
    text = to_markdown(compare_runs(baseline(1), other))
    assert "- the runs are of different suites" in text


def test_json_carries_the_whole_comparison() -> None:
    data = json.loads(to_json(compare_runs(baseline(), regression())))
    assert data["verdict"] == "regression"
    assert data["cases"] == 30 and data["p_value"] < 0.05
    assert len(data["regressed"]) == 10
    assert data["scorers"][0]["scorer"] == "exact_match"
    assert data["delta_ci"][1] < 0


def test_latency_change_is_whole_milliseconds_and_never_negative_zero() -> None:
    assert latency_change(10.0, 20.0) == "+10 ms"
    assert latency_change(20.0, 10.0) == "-10 ms"
    assert latency_change(0.4, 0.0) == "+0 ms"
    assert latency_change(0.0, 0.4) == "+0 ms"
