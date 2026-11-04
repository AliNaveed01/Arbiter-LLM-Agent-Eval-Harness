import pytest

from agentgauge.judge.rubric import Scale
from agentgauge.judge.verdict import Verdict, VerdictError, parse_verdict

FIVE = Scale.model_validate(5)
BINARY = Scale.model_validate("binary")


def test_parses_a_plain_object() -> None:
    assert parse_verdict('{"score": 4, "reasoning": "good"}', FIVE) == Verdict(
        score=4, reasoning="good"
    )


def test_accepts_code_fences_whitespace_and_integral_floats() -> None:
    assert parse_verdict('\n```json\n{"score": 3.0, "reasoning": "ok"}\n```\n', FIVE).score == 3
    assert parse_verdict('```\n{"score": 1, "reasoning": "r"}\n```', BINARY).score == 1


def test_extra_keys_are_ignored() -> None:
    assert parse_verdict('{"score": 1, "reasoning": "r", "confidence": 0.9}', BINARY).score == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "not valid JSON"),
        ('Sure! {"score": 1, "reasoning": "r"}', "not valid JSON"),
        ("[1, 2]", "must be a JSON object"),
        ('{"score": 1}', "'score' and 'reasoning'"),
        ('{"reasoning": "r"}', "'score' and 'reasoning'"),
        ('{"score": "4", "reasoning": "r"}', "must be an integer"),
        ('{"score": 3.5, "reasoning": "r"}', "must be an integer"),
        ('{"score": true, "reasoning": "r"}', "must be an integer"),
        ('{"score": 6, "reasoning": "r"}', "outside the scale"),
        ('{"score": 0, "reasoning": "r"}', "outside the scale"),
        ('{"score": 3, "reasoning": 7}', "reasoning must be a string"),
    ],
)
def test_malformed_replies_are_rejected(text: str, message: str) -> None:
    with pytest.raises(VerdictError, match=message):
        parse_verdict(text, FIVE)


def test_binary_scale_rejects_two() -> None:
    with pytest.raises(VerdictError, match="outside the scale"):
        parse_verdict('{"score": 2, "reasoning": "r"}', BINARY)
