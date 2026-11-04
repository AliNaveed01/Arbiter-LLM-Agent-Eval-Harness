"""Agreement metrics between human labels and judge scores, in pure Python.

Every function takes two equal-length sequences of integer scores, ``human``
(the reference) and ``judge``, plus ``classes``: every score the scale allows.
Passing the classes explicitly keeps matrices the same shape whichever scores
happen to occur in a small sample.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict


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
