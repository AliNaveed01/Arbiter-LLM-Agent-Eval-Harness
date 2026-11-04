import pytest

from agentgauge.calibration.metrics import (
    accuracy,
    bootstrap_kappa_ci,
    calibrate,
    cohens_kappa,
    confusion_matrix,
    per_class_stats,
)
from agentgauge.judge import Scale

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


GOLDEN_LOW = 0.2857142857142858
GOLDEN_HIGH = 0.8979591836734694
MANY_HUMAN = [1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0]
MANY_JUDGE = [1, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0]


def test_bootstrap_is_reproducible_for_a_seed() -> None:
    first = bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY, seed=3)
    assert first == bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY, seed=3)
    assert first != bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY, seed=4)


def test_bootstrap_interval_brackets_the_estimate_and_stays_in_range() -> None:
    ci = bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY)
    kappa = cohens_kappa(MANY_HUMAN, MANY_JUDGE, BINARY)
    assert ci is not None
    assert kappa is not None
    low, high = ci
    assert -1.0 <= low <= kappa <= high <= 1.0


def test_bootstrap_golden_value() -> None:
    # Pins the algorithm (resampling order, percentile rule) so changes are deliberate.
    ci = bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY, resamples=200, seed=0)
    assert ci == pytest.approx((GOLDEN_LOW, GOLDEN_HIGH))


def test_narrower_confidence_gives_a_narrower_interval() -> None:
    wide = bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY, confidence=0.99)
    narrow = bootstrap_kappa_ci(MANY_HUMAN, MANY_JUDGE, BINARY, confidence=0.5)
    assert wide is not None
    assert narrow is not None
    assert wide[1] - wide[0] > narrow[1] - narrow[0]


def test_bootstrap_perfect_agreement_is_a_point() -> None:
    assert bootstrap_kappa_ci([0, 1, 0, 1], [0, 1, 0, 1], BINARY) == (1.0, 1.0)


def test_bootstrap_undefined_everywhere_is_none() -> None:
    assert bootstrap_kappa_ci([1, 1, 1], [1, 1, 1], BINARY) is None


@pytest.mark.parametrize("kwargs", [{"resamples": 0}, {"confidence": 1.0}, {"confidence": 0.0}])
def test_bootstrap_rejects_bad_options(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match=r"resamples|confidence"):
        bootstrap_kappa_ci(HUMAN, JUDGE, BINARY, **kwargs)  # type: ignore[arg-type]


def test_calibrate_binary_report() -> None:
    report = calibrate(HUMAN, JUDGE, Scale.model_validate("binary"))
    assert (report.n, report.weighting, report.classes) == (5, "none", (0, 1))
    assert report.accuracy == pytest.approx(0.8)
    assert report.kappa == pytest.approx(0.32 / 0.52)
    assert report.confusion == ((2, 0), (1, 2))
    assert [c.label for c in report.per_class] == [0, 1]
    assert report.kappa_ci is not None


def test_calibrate_ordinal_uses_quadratic_weighting() -> None:
    report = calibrate([1, 2, 3, 3], [1, 3, 3, 2], Scale.model_validate(3))
    assert report.weighting == "quadratic"
    assert report.kappa == pytest.approx(7 / 11)


def test_calibrate_is_deterministic() -> None:
    scale = Scale.model_validate("binary")
    assert calibrate(MANY_HUMAN, MANY_JUDGE, scale) == calibrate(MANY_HUMAN, MANY_JUDGE, scale)
