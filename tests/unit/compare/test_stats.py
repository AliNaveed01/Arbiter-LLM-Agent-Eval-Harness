import pytest

from agentgauge.compare.stats import mcnemar_exact, paired_bootstrap_ci


@pytest.mark.parametrize(
    ("only_baseline", "only_candidate", "expected"),
    [
        (0, 0, 1.0),  # nothing differs
        (5, 0, 2 / 32),  # five of five one way: 2 * (1/2)^5
        (0, 5, 2 / 32),  # symmetric
        (3, 3, 1.0),  # an even split cannot be significant
        (1, 9, 2 * 11 / 1024),  # n=10, lower tail 1 + 10
        (8, 2, 2 * 56 / 1024),  # n=10, lower tail 1 + 10 + 45
        (1, 0, 1.0),  # a single discordant case proves nothing: 2 * 1/2 capped at 1
    ],
)
def test_mcnemar_matches_hand_computed_values(
    only_baseline: int, only_candidate: int, expected: float
) -> None:
    assert mcnemar_exact(only_baseline, only_candidate) == pytest.approx(expected)


def test_mcnemar_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="negative"):
        mcnemar_exact(-1, 2)


def test_mcnemar_handles_large_counts() -> None:
    assert mcnemar_exact(400, 400) == 1.0
    assert 0 < mcnemar_exact(300, 500) < 1e-6


def test_bootstrap_interval_is_reproducible_for_a_seed() -> None:
    diffs = [0.1 * i - 0.37 for i in range(15)]  # distinct values, so seeds show
    assert paired_bootstrap_ci(diffs, seed=3) == paired_bootstrap_ci(diffs, seed=3)
    assert paired_bootstrap_ci(diffs, seed=3) != paired_bootstrap_ci(diffs, seed=4)


def test_bootstrap_interval_collapses_when_every_difference_is_equal() -> None:
    assert paired_bootstrap_ci([0.0] * 10) == (0.0, 0.0)
    assert paired_bootstrap_ci([-1.0] * 6) == (-1.0, -1.0)


def test_bootstrap_interval_brackets_the_mean_and_narrows_with_more_cases() -> None:
    small = [1.0, -1.0, 0.0, 0.0, 1.0, 0.0]
    large = small * 20
    mean = sum(small) / len(small)
    low_s, high_s = paired_bootstrap_ci(small, seed=1)
    low_l, high_l = paired_bootstrap_ci(large, seed=1)
    assert low_s <= mean <= high_s and low_l <= mean <= high_l
    assert (high_l - low_l) < (high_s - low_s)


def test_a_clear_drop_has_an_interval_below_zero() -> None:
    _, high = paired_bootstrap_ci([-1.0] * 18 + [0.0] * 12, seed=0)
    assert high < 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"differences": []}, "at least one"),
        ({"differences": [0.0], "resamples": 0}, "resamples"),
        ({"differences": [0.0], "confidence": 1.0}, "confidence"),
        ({"differences": [0.0], "confidence": 0.0}, "confidence"),
    ],
)
def test_bootstrap_rejects_bad_arguments(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        paired_bootstrap_ci(**kwargs)  # type: ignore[arg-type]
