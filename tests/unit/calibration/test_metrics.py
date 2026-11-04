import pytest

from agentgauge.calibration.metrics import accuracy, cohens_kappa, confusion_matrix, per_class_stats

BINARY = (0, 1)
HUMAN = [1, 1, 0, 0, 1]
JUDGE = [1, 0, 0, 0, 1]


def test_confusion_matrix_rows_are_human_columns_are_judge() -> None:
    assert confusion_matrix(HUMAN, JUDGE, BINARY) == ((2, 0), (1, 2))


def test_confusion_matrix_keeps_unseen_classes() -> None:
    assert confusion_matrix([1, 3], [1, 3], (1, 2, 3)) == ((1, 0, 0), (0, 0, 0), (0, 0, 1))


def test_accuracy() -> None:
    assert accuracy(HUMAN, JUDGE) == pytest.approx(0.8)
    assert accuracy([1, 2], [1, 2]) == 1.0
    assert accuracy([1, 2], [2, 1]) == 0.0


def test_per_class_precision_and_recall_by_hand() -> None:
    stats = per_class_stats(confusion_matrix(HUMAN, JUDGE, BINARY), BINARY)
    zero, one = stats
    assert (zero.label, zero.recall, zero.support) == (0, 1.0, 2)
    assert zero.precision == pytest.approx(2 / 3)
    assert (one.label, one.precision, one.support) == (1, 1.0, 3)
    assert one.recall == pytest.approx(2 / 3)


def test_undefined_ratios_are_none() -> None:
    stats = per_class_stats(confusion_matrix([1, 1], [1, 1], BINARY), BINARY)
    assert (stats[0].precision, stats[0].recall, stats[0].support) == (None, None, 0)
    # Judge never says 2, humans do; humans never say 3, judge does.
    stats = per_class_stats(confusion_matrix([2, 1], [1, 3], (1, 2, 3)), (1, 2, 3))
    assert stats[1].precision is None
    assert stats[1].recall == 0.0
    assert stats[2].recall is None
    assert stats[2].precision == 0.0


@pytest.mark.parametrize(
    ("human", "judge", "message"),
    [
        ([1], [1, 0], "differ in length"),
        ([], [], "at least one"),
        ([2], [1], "not one of the classes"),
        ([1], [5], "not one of the classes"),
    ],
)
def test_bad_inputs_raise(human: list[int], judge: list[int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        confusion_matrix(human, judge, BINARY)


def test_kappa_by_hand_for_binary() -> None:
    # po = 0.8; chance = 0.4 * 0.6 + 0.6 * 0.4 = 0.48; kappa = 0.32 / 0.52
    assert cohens_kappa(HUMAN, JUDGE, BINARY) == pytest.approx(0.32 / 0.52)


def test_kappa_perfect_and_worse_than_chance() -> None:
    assert cohens_kappa([0, 1, 1, 0], [0, 1, 1, 0], BINARY) == pytest.approx(1.0)
    assert cohens_kappa([0, 1], [1, 0], BINARY) == pytest.approx(-1.0)


def test_kappa_at_chance_level_is_zero() -> None:
    assert cohens_kappa([0, 0, 1, 1], [0, 1, 0, 1], BINARY) == pytest.approx(0.0)


def test_quadratic_weighting_by_hand() -> None:
    # Observed disagreement 0.125, chance disagreement 0.34375 (worked out on paper):
    # kappa = 1 - 0.125 / 0.34375 = 7 / 11.
    human, judge, classes = [1, 2, 3, 3], [1, 3, 3, 2], (1, 2, 3)
    assert cohens_kappa(human, judge, classes, "quadratic") == pytest.approx(7 / 11)


def test_weighting_matters_for_near_misses() -> None:
    human = [1, 2, 3, 4, 5, 5]
    near = [2, 3, 4, 5, 4, 4]
    classes = (1, 2, 3, 4, 5)
    unweighted = cohens_kappa(human, near, classes)
    weighted = cohens_kappa(human, near, classes, "quadratic")
    assert unweighted is not None
    assert weighted is not None
    assert weighted > unweighted


def test_binary_quadratic_equals_unweighted() -> None:
    assert cohens_kappa(HUMAN, JUDGE, BINARY, "quadratic") == pytest.approx(
        cohens_kappa(HUMAN, JUDGE, BINARY) or 0.0
    )


def test_kappa_is_undefined_when_everyone_used_one_score() -> None:
    assert cohens_kappa([1, 1, 1], [1, 1, 1], BINARY) is None
    assert cohens_kappa([3, 3], [3, 3], (1, 2, 3), "quadratic") is None
