from datetime import UTC, datetime

import pytest

from agentgauge.compare import CompareError, pair_runs
from agentgauge.core.models import CaseResult, RunResult, Score


def case(case_id: str, passed: bool = True, error: str | None = None) -> CaseResult:
    score = Score(scorer="s", value=float(passed), passed=passed)
    return CaseResult(case_id=case_id, scores=(score,), error=error)


def run(*cases: CaseResult, suite: str = "suite", run_id: str = "r") -> RunResult:
    return RunResult(
        run_id=run_id,
        suite_name=suite,
        model="m",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=cases,
    )


def test_cases_are_paired_by_id_in_baseline_order() -> None:
    base = run(case("a"), case("b"), case("c"))
    cand = run(case("c", passed=False), case("a"), case("b"))
    pairing = pair_runs(base, cand)
    assert [p.case_id for p in pairing.pairs] == ["a", "b", "c"]
    assert pairing.pairs[2].baseline.passed and not pairing.pairs[2].candidate.passed
    assert pairing.only_in_baseline == () and pairing.only_in_candidate == ()
    assert pairing.warnings == ()


def test_cases_in_only_one_run_are_listed_and_left_out() -> None:
    pairing = pair_runs(run(case("a"), case("old")), run(case("a"), case("new")))
    assert [p.case_id for p in pairing.pairs] == ["a"]
    assert pairing.only_in_baseline == ("old",)
    assert pairing.only_in_candidate == ("new",)


def test_an_errored_case_counts_as_failed() -> None:
    pairing = pair_runs(run(case("a")), run(case("a", error="timeout")))
    assert pairing.pairs[0].candidate.passed is False


def test_a_suite_name_mismatch_is_a_warning_not_an_error() -> None:
    pairing = pair_runs(run(case("a"), suite="old"), run(case("a"), suite="new"))
    assert len(pairing.warnings) == 1 and "'old' and 'new'" in pairing.warnings[0]


def test_runs_with_no_shared_cases_are_refused() -> None:
    with pytest.raises(CompareError, match="share no case ids"):
        pair_runs(run(case("a")), run(case("b")))


@pytest.mark.parametrize("which", ["baseline", "candidate"])
def test_repeated_case_ids_are_refused(which: str) -> None:
    doubled = run(case("a"), case("a"))
    single = run(case("a"))
    args = (doubled, single) if which == "baseline" else (single, doubled)
    with pytest.raises(CompareError, match=f"the {which} run has repeated case ids: a"):
        pair_runs(*args)
