import pytest
from pydantic import ValidationError

from agentgauge.core.models import Message, TestCase
from agentgauge.judge import Rubric, Scale, render_prompt
from agentgauge.judge.prompts import SYSTEM_PROMPT, TEMPLATES


def _rubric(**kwargs: object) -> Rubric:
    base: dict[str, object] = {
        "name": "helpfulness",
        "criteria": ("answers the question", "is polite"),
        "scale": Scale.model_validate(5),
    }
    return Rubric.model_validate({**base, **kwargs})


def test_v1_prompt_contains_every_input() -> None:
    case = TestCase(id="c", input="What is 2 + 2?", expected="4")
    system, user = render_prompt(_rubric(), case, "four")
    assert system == Message(role="system", content=SYSTEM_PROMPT)
    assert user.role == "user"
    for expected in (
        "helpfulness",
        "- answers the question\n- is polite",
        "an integer from 1 (worst) to 5 (best)",
        "user: What is 2 + 2?",
        "Reference answer:\n4",
        "Response to judge:\nfour",
    ):
        assert expected in user.content


def test_binary_scale_and_missing_reference() -> None:
    rubric = _rubric(scale="binary")
    _, user = render_prompt(rubric, TestCase(id="c", input="q"), "a")
    assert "0 (fails the criteria) or 1 (meets them)" in user.content
    assert "(none given)" in user.content


def test_multi_message_input_is_a_transcript() -> None:
    case = TestCase(
        id="c",
        input=[Message(role="user", content="hi"), Message(role="assistant", content="hello")],
    )
    _, user = render_prompt(_rubric(), case, "x")
    assert "user: hi\nassistant: hello" in user.content


def test_rendering_is_deterministic_and_keeps_braces_in_values() -> None:
    case = TestCase(id="c", input='{"a": $1}')
    first = render_prompt(_rubric(), case, "{x}")
    assert first == render_prompt(_rubric(), case, "{x}")
    assert '{"a": $1}' in first[1].content


def test_custom_template_replaces_the_user_message_only() -> None:
    rubric = _rubric(template="Judge $output for $rubric", prompt_version="mine-1")
    system, user = render_prompt(rubric, TestCase(id="c", input="q"), "A")
    assert system.content == SYSTEM_PROMPT
    assert user.content == "Judge A for helpfulness"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prompt_version": "v99"}, "unknown prompt_version"),
        ({"template": "hello $nope"}, "unknown placeholders"),
        ({"template": "costs $5"}, "stray '\\$'"),
    ],
)
def test_unusable_templates_are_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _rubric(**kwargs)


def test_builtin_v1_uses_only_known_placeholders() -> None:
    assert _rubric(prompt_version="v1").prompt_version in TEMPLATES
