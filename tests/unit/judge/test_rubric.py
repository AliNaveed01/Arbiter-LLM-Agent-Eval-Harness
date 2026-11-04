import pytest
from pydantic import ValidationError

from agentgauge.judge import Rubric, Scale


def test_binary_scale_values() -> None:
    assert Scale.model_validate("binary").values == (0, 1)


def test_ordinal_scale_from_a_number() -> None:
    scale = Scale.model_validate(5)
    assert (scale.kind, scale.levels) == ("ordinal", 5)
    assert scale.values == (1, 2, 3, 4, 5)


@pytest.mark.parametrize("bad", [1, 11, True, "likert", {"kind": "binary", "levels": 3}])
def test_invalid_scales_are_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        Scale.model_validate(bad)


def test_rubric_defaults_and_thresholds() -> None:
    binary = Rubric(name="r", criteria=("is correct",), scale=Scale.model_validate("binary"))
    assert (binary.prompt_version, binary.template, binary.threshold) == ("v1", None, 1)
    five = Rubric(name="r", criteria=("c",), scale=Scale.model_validate(5))
    four = Rubric(name="r", criteria=("c",), scale=Scale.model_validate(4))
    assert (five.threshold, four.threshold) == (3, 3)


def test_explicit_pass_at_must_be_on_the_scale() -> None:
    scale = Scale.model_validate(5)
    assert Rubric(name="r", criteria=("c",), scale=scale, pass_at=4).threshold == 4
    with pytest.raises(ValidationError, match="pass_at"):
        Rubric(name="r", criteria=("c",), scale=scale, pass_at=6)


@pytest.mark.parametrize("criteria", [(), ("  ",)])
def test_criteria_must_be_present_and_not_blank(criteria: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        Rubric(name="r", criteria=criteria, scale=Scale.model_validate("binary"))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Rubric.model_validate({"name": "r", "criteria": ["c"], "scale": "binary", "extra": 1})
