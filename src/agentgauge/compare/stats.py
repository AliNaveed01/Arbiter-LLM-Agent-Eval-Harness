"""The statistics behind a comparison, in pure Python."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def mcnemar_exact(only_baseline: int, only_candidate: int) -> float:
    """Two-sided exact McNemar p-value for paired pass/fail results.

    ``only_baseline`` counts cases the baseline passed and the candidate failed;
    ``only_candidate`` the reverse. Cases both passed or both failed carry no information
    about a difference and are left out. Under "no difference" each discordant case is
    equally likely to go either way, so the smaller count is binomial with p = 0.5; the
    p-value doubles its lower tail and is capped at 1. It is 1.0 when there are no
    discordant cases.
    """
    if only_baseline < 0 or only_candidate < 0:
        raise ValueError("counts cannot be negative")
    n = only_baseline + only_candidate
    if n == 0:
        return 1.0
    smaller = min(only_baseline, only_candidate)
    tail = sum(math.comb(n, k) for k in range(smaller + 1))
    return min(1.0, 2 * tail / 2**n)


def paired_bootstrap_ci(
    differences: Sequence[float],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """A percentile bootstrap interval for the mean of per-case differences.

    Cases are resampled with replacement from a generator seeded with ``seed``, so the
    interval is reproducible. Because each difference is candidate minus baseline on one
    case, the pairing is kept and case difficulty cancels out. With few cases the interval
    is wide, which is the point.
    """
    if not differences:
        raise ValueError("need at least one difference")
    if resamples < 1:
        raise ValueError("resamples must be at least 1")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    rng = random.Random(seed)
    n = len(differences)
    means = sorted(
        math.fsum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)
    )
    tail = (1 - confidence) / 2
    low = means[math.floor(tail * (len(means) - 1))]
    high = means[math.ceil((1 - tail) * (len(means) - 1))]
    return low, high
