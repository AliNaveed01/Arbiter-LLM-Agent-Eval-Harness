from datetime import UTC, datetime

import pytest

from agentgauge.compare import CompareError, compare_runs
from agentgauge.core.models import CaseResult, RunResult, Score


def case(
    case_id: str, passed: bool, *, value: float | None = None, latency: float | None = None
) -> CaseResult:
    score = Score(
        scorer="exact_match", value=float(passed) if value is None else value, passed=passed
    )
    return CaseResult(case_id=case_id, scores=(score,), latency_ms=latency)


def run(results: list[CaseResult], run_id: str = "r", suite: str = "s") -> RunResult:
    return RunResult(
        run_id=run_id,
        suite_name=suite,
        model="m-" + run_id,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=tuple(results),
    )


def runs(total: int, regress: int, improve: int) -> tuple[RunResult, RunResult]:
    """``regress`` cases pass then fail, ``improve`` fail then pass, the rest always pass."""
    base: list[CaseResult] = []
    cand: list[CaseResult] = []
    for i in range(total):
        if i < regress:
            states = (True, False)
        elif i < regress + improve:
            states = (False, True)
        else:
            states = (True, True)
        base.append(case(f"c{i}", states[0]))
        cand.append(case(f"c{i}", states[1]))
    return run(base, "base"), run(cand, "cand")


def test_a_clear_drop_is_a_regression() -> None:
    result = compare_runs(*runs(30, regress=10, improve=0))
    assert result.verdict == "regression"
    assert result.baseline_pass_rate == 1.0 and result.candidate_pass_rate == pytest.approx(20 / 30)
    assert result.delta == pytest.approx(-1 / 3)
    assert result.p_value == pytest.approx(2 / 1024)
    assert result.delta_ci[1] < 0
    assert len(result.regressed) == 10 and result.improved == ()


def test_a_small_drop_that_could_be_noise_is_not_flagged() -> None:
    result = compare_runs(*runs(30, regress=3, improve=1))
    assert result.verdict == "unchanged"
    assert result.p_value > 0.05 and result.delta < 0


def test_one_failure_in_a_small_suite_is_never_significant() -> None:
    result = compare_runs(*runs(5, regress=1, improve=0))
    assert result.verdict == "unchanged" and result.p_value == 1.0


def test_a_clear_gain_is_an_improvement() -> None:
    result = compare_runs(*runs(30, regress=0, improve=10))
    assert result.verdict == "improvement"
    assert len(result.improved) == 10 and result.regressed == ()


def test_identical_runs_are_unchanged() -> None:
    result = compare_runs(*runs(10, regress=0, improve=0))
    assert result.verdict == "unchanged" and result.delta == 0.0 and result.p_value == 1.0


def test_a_significant_drop_within_max_drop_is_tolerated() -> None:
    base, cand = runs(100, regress=10, improve=0)
    assert compare_runs(base, cand).verdict == "regression"
    assert compare_runs(base, cand, max_drop=0.10).verdict == "unchanged"  # exactly the allowance
    assert compare_runs(base, cand, max_drop=0.05).verdict == "regression"


def test_alpha_sets_how_much_evidence_is_needed() -> None:
    base, cand = runs(30, regress=6, improve=0)  # p = 2/64 = 0.03125
    assert compare_runs(base, cand, alpha=0.05).verdict == "regression"
    assert compare_runs(base, cand, alpha=0.01).verdict == "unchanged"


def test_scorer_deltas_use_the_cases_both_runs_scored() -> None:
    base = run([case("a", True, value=1.0), case("b", True, value=0.8), case("c", True, value=0.6)])
    cand = run(
        [case("a", True, value=0.5), case("b", True, value=0.4), case("c", True, value=0.3)],
        "c",
    )
    result = compare_runs(base, cand, seed=1)
    (scorer,) = result.scorers
    assert scorer.scorer == "exact_match" and scorer.cases == 3
    assert scorer.baseline_mean == pytest.approx(0.8) and scorer.candidate_mean == pytest.approx(
        0.4
    )
    assert scorer.delta == pytest.approx(-0.4)
    assert scorer.delta_ci[0] <= scorer.delta <= scorer.delta_ci[1]


def test_a_scorer_in_only_one_run_is_warned_about() -> None:
    extra = Score(scorer="contains", value=1.0, passed=True)
    base = run(
        [CaseResult(case_id="a", scores=(extra, Score(scorer="exact_match", value=1, passed=True)))]
    )
    cand = run([case("a", True)], "c")
    result = compare_runs(base, cand)
    assert [s.scorer for s in result.scorers] == ["exact_match"]
    assert any("'contains' appears in only one" in w for w in result.warnings)


def test_latency_is_averaged_over_cases_with_both_measurements() -> None:
    base = run([case("a", True, latency=100.0), case("b", True, latency=300.0), case("c", True)])
    cand = run(
        [
            case("a", True, latency=200.0),
            case("b", True, latency=400.0),
            case("c", True, latency=9.0),
        ],
        "c",
    )
    result = compare_runs(base, cand)
    assert (result.baseline_latency_ms, result.candidate_latency_ms) == (200.0, 300.0)
    assert (
        compare_runs(run([case("a", True)]), run([case("a", True)], "c")).baseline_latency_ms
        is None
    )


def test_unshared_cases_and_a_suite_mismatch_are_reported() -> None:
    base = run([case("a", True), case("old", True)], suite="old-name")
    cand = run([case("a", True), case("new", True)], "c", suite="new-name")
    result = compare_runs(base, cand)
    assert result.cases == 1 and result.suite_name == "new-name"
    assert result.only_in_baseline == ("old",) and result.only_in_candidate == ("new",)
    assert any("different suites" in w for w in result.warnings)


def test_the_comparison_is_deterministic_for_a_seed() -> None:
    pair = runs(30, regress=7, improve=2)
    assert compare_runs(*pair, seed=5) == compare_runs(*pair, seed=5)


def test_runs_that_share_no_cases_cannot_be_compared() -> None:
    with pytest.raises(CompareError):
        compare_runs(run([case("a", True)]), run([case("b", True)], "c"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"alpha": 0.0}, "alpha"),
        ({"alpha": 1.0}, "alpha"),
        ({"max_drop": -0.1}, "max_drop"),
        ({"max_drop": 1.1}, "max_drop"),
    ],
)
def test_bad_thresholds_are_rejected(kwargs: dict[str, float], message: str) -> None:
    base, cand = runs(4, 0, 0)
    with pytest.raises(ValueError, match=message):
        compare_runs(
            base, cand, alpha=kwargs.get("alpha", 0.05), max_drop=kwargs.get("max_drop", 0.0)
        )
