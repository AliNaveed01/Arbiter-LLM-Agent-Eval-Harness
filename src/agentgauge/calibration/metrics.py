"""Agreement metrics between human labels and judge scores, in pure Python.

Every function takes two equal-length sequences of integer scores, ``human``
(the reference) and ``judge``, plus ``classes``: every score the scale allows.
Passing the classes explicitly keeps matrices the same shape whichever scores
happen to occur in a small sample.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentgauge.judge.rubric import Scale

Weighting = Literal["none", "quadratic"]


class ClassStats(BaseModel):
    """Precision and recall for one class, treating the human label as truth.

    ``precision`` is ``None`` when the judge never gave this score, and
    ``recall`` is ``None`` when no human did, because the ratio is undefined.
    """

    model_config = ConfigDict(frozen=True)

    label: int
    precision: float | None
    recall: float | None
    support: int


def _check(human: Sequence[int], judge: Sequence[int], classes: Sequence[int]) -> None:
    if len(human) != len(judge):
        raise ValueError(f"human and judge scores differ in length ({len(human)} vs {len(judge)})")
    if not human:
        raise ValueError("need at least one scored case")
    allowed = set(classes)
    for score in (*human, *judge):
        if score not in allowed:
            raise ValueError(f"score {score} is not one of the classes {list(classes)}")


def confusion_matrix(
    human: Sequence[int], judge: Sequence[int], classes: Sequence[int]
) -> tuple[tuple[int, ...], ...]:
    """Counts with a row per human score and a column per judge score."""
    _check(human, judge, classes)
    index = {label: i for i, label in enumerate(classes)}
    counts = [[0] * len(classes) for _ in classes]
    for h, j in zip(human, judge, strict=True):
        counts[index[h]][index[j]] += 1
    return tuple(tuple(row) for row in counts)


def accuracy(human: Sequence[int], judge: Sequence[int]) -> float:
    """The fraction of cases where the judge's score equals the human's."""
    _check(human, judge, sorted({*human, *judge}))
    return sum(h == j for h, j in zip(human, judge, strict=True)) / len(human)


def per_class_stats(
    matrix: Sequence[Sequence[int]], classes: Sequence[int]
) -> tuple[ClassStats, ...]:
    """Precision, recall and support for each class of a confusion matrix."""
    stats: list[ClassStats] = []
    for i, label in enumerate(classes):
        true_positive = matrix[i][i]
        actual = sum(matrix[i])
        predicted = sum(row[i] for row in matrix)
        stats.append(
            ClassStats(
                label=label,
                precision=true_positive / predicted if predicted else None,
                recall=true_positive / actual if actual else None,
                support=actual,
            )
        )
    return tuple(stats)


def cohens_kappa(
    human: Sequence[int],
    judge: Sequence[int],
    classes: Sequence[int],
    weighting: Weighting = "none",
) -> float | None:
    """Cohen's kappa: agreement beyond what the two raters' score habits give by chance.

    ``weighting="quadratic"`` penalises a disagreement by the squared distance
    between the scores, so a 4 against a 5 costs far less than a 1 against a 5;
    use it for ordinal scales. 1 is perfect agreement, 0 is chance level and
    negative is worse than chance.

    Returns ``None`` when kappa is undefined: when chance agreement is already
    perfect, which happens when both raters used a single score for every case.
    """
    matrix = confusion_matrix(human, judge, classes)
    n = len(human)
    size = len(classes)
    row_totals = [sum(row) / n for row in matrix]
    col_totals = [sum(matrix[i][j] for i in range(size)) / n for j in range(size)]
    span = (classes[-1] - classes[0]) or 1
    observed = expected = 0.0
    for i in range(size):
        for j in range(size):
            if weighting == "quadratic":
                weight = ((classes[i] - classes[j]) / span) ** 2
            else:
                weight = 0.0 if i == j else 1.0
            observed += weight * matrix[i][j] / n
            expected += weight * row_totals[i] * col_totals[j]
    if expected == 0.0:
        return None
    return 1.0 - observed / expected


def bootstrap_kappa_ci(
    human: Sequence[int],
    judge: Sequence[int],
    classes: Sequence[int],
    weighting: Weighting = "none",
    *,
    resamples: int = 1000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float] | None:
    """A percentile bootstrap confidence interval for kappa.

    Cases are resampled with replacement ``resamples`` times from a generator
    seeded with ``seed``, so the interval is reproducible. Resamples where
    kappa is undefined are skipped; ``None`` is returned if all of them are.
    With few cases the interval is wide, which is the point: it shows how little
    a small label set can tell you.
    """
    _check(human, judge, classes)
    if resamples < 1:
        raise ValueError("resamples must be at least 1")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    rng = random.Random(seed)
    n = len(human)
    values: list[float] = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        kappa = cohens_kappa(
            [human[i] for i in picks], [judge[i] for i in picks], classes, weighting
        )
        if kappa is not None:
            values.append(kappa)
    if not values:
        return None
    values.sort()
    tail = (1 - confidence) / 2
    low = values[math.floor(tail * (len(values) - 1))]
    high = values[math.ceil((1 - tail) * (len(values) - 1))]
    return low, high


class CalibrationReport(BaseModel):
    """How well a judge's scores agree with human labels."""

    model_config = ConfigDict(frozen=True)

    n: int
    scale: Scale
    weighting: Weighting
    accuracy: float
    kappa: float | None
    kappa_ci: tuple[float, float] | None
    classes: tuple[int, ...]
    confusion: tuple[tuple[int, ...], ...]
    per_class: tuple[ClassStats, ...]


def calibrate(
    human: Sequence[int],
    judge: Sequence[int],
    scale: Scale,
    *,
    resamples: int = 1000,
    seed: int = 0,
) -> CalibrationReport:
    """Compare ``judge`` scores with ``human`` labels on ``scale``.

    Ordinal scales use quadratic-weighted kappa; binary scales use plain kappa.
    """
    classes = scale.values
    weighting: Weighting = "quadratic" if scale.kind == "ordinal" else "none"
    matrix = confusion_matrix(human, judge, classes)
    return CalibrationReport(
        n=len(human),
        scale=scale,
        weighting=weighting,
        accuracy=accuracy(human, judge),
        kappa=cohens_kappa(human, judge, classes, weighting),
        kappa_ci=bootstrap_kappa_ci(
            human, judge, classes, weighting, resamples=resamples, seed=seed
        ),
        classes=classes,
        confusion=matrix,
        per_class=per_class_stats(matrix, classes),
    )
