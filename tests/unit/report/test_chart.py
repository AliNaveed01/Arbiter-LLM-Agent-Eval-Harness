import re
from datetime import UTC, datetime

import pytest

from agentgauge.compare import compare_runs
from agentgauge.compare.report import Comparison
from agentgauge.core.models import CaseResult, RunResult, Score
from agentgauge.report.chart import axis_extent, change_chart, description
from agentgauge.report.comparison import comparison_section


def run(states: list[bool], run_id: str) -> RunResult:
    results = tuple(
        CaseResult(case_id=f"c{i}", scores=(Score(scorer="s", value=float(ok), passed=ok),))
        for i, ok in enumerate(states)
    )
    return RunResult(
        run_id=run_id,
        suite_name="s",
        model="m",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=results,
    )


def make(total: int, regress: int, improve: int = 0) -> Comparison:
    """The first ``regress`` cases go pass to fail, the next ``improve`` fail to pass."""
    before: list[bool] = []
    after: list[bool] = []
    for i in range(total):
        if i < regress:
            before.append(True)
            after.append(False)
        elif i < regress + improve:
            before.append(False)
            after.append(True)
        else:
            before.append(True)
            after.append(True)
    return compare_runs(run(before, "b"), run(after, "a"), resamples=200)


def centre(svg: str) -> float:
    match = re.search(r'cx="([-0-9.]+)"', svg)
    assert match is not None
    return float(match.group(1))


def zero_line(svg: str) -> float:
    match = re.search(r'x1="([-0-9.]+)"[^>]*class="zero"', svg)
    assert match is not None
    return float(match.group(1))


def whisker(svg: str) -> tuple[float, float]:
    match = re.search(r'x1="([-0-9.]+)" x2="([-0-9.]+)"[^>]*class="whisker', svg)
    assert match is not None
    return float(match.group(1)), float(match.group(2))


def test_the_text_alternative_states_the_numbers() -> None:
    c = make(30, 10)
    out = change_chart(c)
    assert 'role="img"' in out and 'aria-label="Change in pass rate -33.3 points' in out
    assert "<title>Change in pass rate -33.3 points, 95% interval" in out
    assert "zero means no change" in description(c)


def test_a_regression_draws_the_dot_inside_its_whisker_left_of_zero() -> None:
    out = change_chart(make(30, 10))
    low, high = whisker(out)
    assert low <= centre(out) <= high < zero_line(out)
    assert "mark-fail" in out and "mark-pass" not in out


def test_an_improvement_is_drawn_right_of_zero() -> None:
    out = change_chart(make(30, 0, 10))
    assert centre(out) > zero_line(out) and "mark-pass" in out


def test_no_change_is_a_dot_on_zero() -> None:
    out = change_chart(make(10, 0))
    assert centre(out) == zero_line(out) and "mark-flat" in out and "+0.0 points" in out


@pytest.mark.parametrize("regress", [0, 2, 10, 25, 30])
def test_the_axis_is_a_round_number_that_holds_the_interval(regress: int) -> None:
    c = make(30, regress)
    reach = max(abs(c.delta_ci[0]), abs(c.delta_ci[1])) * 100
    assert axis_extent(c) in (5, 10, 20, 25, 50, 100)
    assert axis_extent(c) >= reach or axis_extent(c) == 100


def test_the_chart_has_no_scripts_or_external_references() -> None:
    out = change_chart(make(30, 10))
    assert "<script" not in out and "href" not in out and "http" not in out


def test_the_comparison_section_includes_the_chart_before_the_table() -> None:
    out = comparison_section(make(30, 10))
    assert out.index("<figure") < out.index("<table>")
