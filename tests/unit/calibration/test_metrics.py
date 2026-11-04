import pytest

from agentgauge.calibration.metrics import accuracy, confusion_matrix, per_class_stats

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
