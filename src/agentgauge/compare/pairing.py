"""Match the cases of two runs so every comparison is paired."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict

from agentgauge.core.models import CaseResult, RunResult


class CompareError(ValueError):
    """The two runs cannot be compared."""


class CasePair(BaseModel):
    """The same case in the baseline run and in the candidate run."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    baseline: CaseResult
    candidate: CaseResult


class Pairing(BaseModel):
    """The cases two runs share, and the ones only one of them has."""

    model_config = ConfigDict(frozen=True)

    pairs: tuple[CasePair, ...]
    only_in_baseline: tuple[str, ...] = ()
    only_in_candidate: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _by_id(run: RunResult, label: str) -> dict[str, CaseResult]:
    counts = Counter(result.case_id for result in run.results)
    repeated = sorted(case_id for case_id, count in counts.items() if count > 1)
    if repeated:
        raise CompareError(f"the {label} run has repeated case ids: {', '.join(repeated)}")
    return {result.case_id: result for result in run.results}


def pair_runs(baseline: RunResult, candidate: RunResult) -> Pairing:
    """Pair the cases of ``baseline`` and ``candidate`` by case id.

    Pairs follow the baseline's order. A case that errored counts as failed, as it does
    everywhere else. Runs of differently named suites are paired anyway, with a warning,
    because renaming a suite is not a reason to lose the history.
    """
    before = _by_id(baseline, "baseline")
    after = _by_id(candidate, "candidate")
    pairs = tuple(
        CasePair(case_id=case_id, baseline=result, candidate=after[case_id])
        for case_id, result in before.items()
        if case_id in after
    )
    if not pairs:
        raise CompareError("the two runs share no case ids, so there is nothing to compare")
    warnings: list[str] = []
    if baseline.suite_name != candidate.suite_name:
        warnings.append(
            f"the runs are of different suites ({baseline.suite_name!r} and "
            f"{candidate.suite_name!r})"
        )
    return Pairing(
        pairs=pairs,
        only_in_baseline=tuple(case_id for case_id in before if case_id not in after),
        only_in_candidate=tuple(case_id for case_id in after if case_id not in before),
        warnings=tuple(warnings),
    )
