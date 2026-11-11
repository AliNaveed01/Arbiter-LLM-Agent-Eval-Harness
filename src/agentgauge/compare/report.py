"""Compare two runs and say whether the candidate is a significant regression."""

from __future__ import annotations

import statistics
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentgauge.compare.pairing import CasePair, pair_runs
from agentgauge.compare.stats import mcnemar_exact, paired_bootstrap_ci
from agentgauge.core.models import RunResult

Verdict = Literal["regression", "improvement", "unchanged"]


class ScorerDelta(BaseModel):
    """How one scorer's mean value moved between the runs, over the cases it scored in both."""

    model_config = ConfigDict(frozen=True)

    scorer: str
    cases: int
    baseline_mean: float
    candidate_mean: float
    delta: float
    delta_ci: tuple[float, float]


class Comparison(BaseModel):
    """The outcome of comparing a candidate run with a baseline run.

    ``delta`` is candidate minus baseline, so a negative number is a drop. ``p_value`` is
    the exact McNemar p-value on the paired pass/fail results.
    """

    model_config = ConfigDict(frozen=True)

    baseline_id: str
    candidate_id: str
    baseline_model: str
    candidate_model: str
    suite_name: str
    cases: int
    baseline_pass_rate: float
    candidate_pass_rate: float
    delta: float
    delta_ci: tuple[float, float]
    regressed: tuple[str, ...]
    improved: tuple[str, ...]
    p_value: float
    alpha: float
    max_drop: float
    resamples: int
    seed: int
    verdict: Verdict
    scorers: tuple[ScorerDelta, ...] = ()
    baseline_latency_ms: float | None = None
    candidate_latency_ms: float | None = None
    only_in_baseline: tuple[str, ...] = ()
    only_in_candidate: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _scorer_deltas(
    pairs: tuple[CasePair, ...], *, resamples: int, seed: int
) -> tuple[tuple[ScorerDelta, ...], list[str]]:
    before: dict[str, list[float]] = {}
    after: dict[str, list[float]] = {}
    seen_in_baseline: set[str] = set()
    seen_in_candidate: set[str] = set()
    for pair in pairs:
        base = {s.scorer: s.value for s in pair.baseline.scores}
        cand = {s.scorer: s.value for s in pair.candidate.scores}
        seen_in_baseline |= base.keys()
        seen_in_candidate |= cand.keys()
        for name in base.keys() & cand.keys():
            before.setdefault(name, []).append(base[name])
            after.setdefault(name, []).append(cand[name])
    deltas: list[ScorerDelta] = []
    for name in sorted(before):
        diffs = [c - b for b, c in zip(before[name], after[name], strict=True)]
        deltas.append(
            ScorerDelta(
                scorer=name,
                cases=len(diffs),
                baseline_mean=statistics.fmean(before[name]),
                candidate_mean=statistics.fmean(after[name]),
                delta=statistics.fmean(diffs),
                delta_ci=paired_bootstrap_ci(diffs, resamples=resamples, seed=seed),
            )
        )
    warnings = [
        f"scorer {name!r} appears in only one of the runs and was not compared"
        for name in sorted(seen_in_baseline ^ seen_in_candidate)
    ]
    return tuple(deltas), warnings


def _mean_latency(pairs: tuple[CasePair, ...]) -> tuple[float | None, float | None]:
    both = [
        (p.baseline.latency_ms, p.candidate.latency_ms)
        for p in pairs
        if p.baseline.latency_ms is not None and p.candidate.latency_ms is not None
    ]
    if not both:
        return None, None
    return statistics.fmean(b for b, _ in both), statistics.fmean(c for _, c in both)


def compare_runs(
    baseline: RunResult,
    candidate: RunResult,
    *,
    alpha: float = 0.05,
    max_drop: float = 0.0,
    resamples: int = 2000,
    seed: int = 0,
) -> Comparison:
    """Compare ``candidate`` with ``baseline`` on the cases they share.

    The verdict is ``regression`` only when the difference is statistically significant
    (exact McNemar p-value below ``alpha``) and the pass rate fell by more than
    ``max_drop``. ``improvement`` is the mirror image, without a tolerance. Anything else
    is ``unchanged``: a drop that could be noise, or one smaller than you said you accept.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 <= max_drop <= 1:
        raise ValueError("max_drop must be between 0 and 1")
    pairing = pair_runs(baseline, candidate)
    pairs = pairing.pairs
    regressed = tuple(p.case_id for p in pairs if p.baseline.passed and not p.candidate.passed)
    improved = tuple(p.case_id for p in pairs if p.candidate.passed and not p.baseline.passed)
    diffs = [int(p.candidate.passed) - int(p.baseline.passed) for p in pairs]
    delta = sum(diffs) / len(pairs)
    p_value = mcnemar_exact(len(regressed), len(improved))
    significant = p_value < alpha
    verdict: Verdict = "unchanged"
    if significant and delta < 0 and -delta > max_drop:
        verdict = "regression"
    elif significant and delta > 0:
        verdict = "improvement"
    scorers, scorer_warnings = _scorer_deltas(pairs, resamples=resamples, seed=seed)
    base_latency, cand_latency = _mean_latency(pairs)
    return Comparison(
        baseline_id=baseline.run_id,
        candidate_id=candidate.run_id,
        baseline_model=baseline.model,
        candidate_model=candidate.model,
        suite_name=candidate.suite_name,
        cases=len(pairs),
        baseline_pass_rate=sum(p.baseline.passed for p in pairs) / len(pairs),
        candidate_pass_rate=sum(p.candidate.passed for p in pairs) / len(pairs),
        delta=delta,
        delta_ci=paired_bootstrap_ci([float(d) for d in diffs], resamples=resamples, seed=seed),
        regressed=regressed,
        improved=improved,
        p_value=p_value,
        alpha=alpha,
        max_drop=max_drop,
        resamples=resamples,
        seed=seed,
        verdict=verdict,
        scorers=scorers,
        baseline_latency_ms=base_latency,
        candidate_latency_ms=cand_latency,
        only_in_baseline=pairing.only_in_baseline,
        only_in_candidate=pairing.only_in_candidate,
        warnings=(*pairing.warnings, *scorer_warnings),
    )
