import asyncio

import pytest

from agentgauge.core import ModelOutput, Score, ScorerSpec, TestCase
from agentgauge.scorers import Scorer, ScorerConfigError, create_scorer


def score(scorer: Scorer, text: str, expected: str | None = None) -> Score:
    case = TestCase(id="c", input="q", expected=expected)
    return asyncio.run(scorer.score(case, ModelOutput(text=text, latency_ms=0)))


class TestExactMatch:
    def test_matches_identical_text(self) -> None:
        result = score(create_scorer("exact_match"), "Paris", "Paris")
        assert (result.scorer, result.value, result.passed) == ("exact_match", 1.0, True)
        assert result.reason is None

    def test_mismatch_fails_with_reason(self) -> None:
        result = score(create_scorer("exact_match"), "London", "Paris")
        assert (result.value, result.passed) == (0.0, False)
        assert result.reason == "expected 'Paris'"

    def test_edge_whitespace_ignored_by_default(self) -> None:
        assert score(create_scorer("exact_match"), "  Paris\n", "Paris").passed

    def test_strip_can_be_disabled(self) -> None:
        scorer = create_scorer(ScorerSpec(name="exact_match", params={"strip": False}))
        assert not score(scorer, "Paris\n", "Paris").passed

    def test_case_sensitive_by_default(self) -> None:
        assert not score(create_scorer("exact_match"), "paris", "Paris").passed

    def test_case_insensitive_option(self) -> None:
        scorer = create_scorer(ScorerSpec(name="exact_match", params={"case_sensitive": False}))
        assert score(scorer, "PARIS", "Paris").passed

    def test_inner_whitespace_is_significant(self) -> None:
        assert not score(create_scorer("exact_match"), "New  York", "New York").passed

    def test_empty_output_matches_empty_expected(self) -> None:
        assert score(create_scorer("exact_match"), "", "").passed

    def test_missing_expected_fails_with_reason(self) -> None:
        result = score(create_scorer("exact_match"), "x")
        assert not result.passed
        assert result.reason == "case has no expected value"


class TestContains:
    def test_substring_passes(self) -> None:
        assert score(create_scorer("contains"), "The capital is Paris.", "Paris").passed

    def test_missing_substring_fails_with_reason(self) -> None:
        result = score(create_scorer("contains"), "The capital is Rome.", "Paris")
        assert not result.passed
        assert result.reason == "output does not contain 'Paris'"

    def test_case_sensitive_by_default(self) -> None:
        assert not score(create_scorer("contains"), "paris", "Paris").passed

    def test_case_insensitive_option(self) -> None:
        scorer = create_scorer(ScorerSpec(name="contains", params={"case_sensitive": False}))
        assert score(scorer, "PARIS is nice", "paris").passed

    def test_empty_expected_always_matches(self) -> None:
        assert score(create_scorer("contains"), "anything", "").passed

    def test_empty_output_does_not_contain_text(self) -> None:
        assert not score(create_scorer("contains"), "", "x").passed

    def test_missing_expected_fails_with_reason(self) -> None:
        result = score(create_scorer("contains"), "x")
        assert (result.passed, result.reason) == (False, "case has no expected value")


def regex(**params: object) -> Scorer:
    return create_scorer(ScorerSpec(name="regex", params=dict(params)))


class TestRegex:
    def test_pattern_param_searches_anywhere(self) -> None:
        assert score(regex(pattern=r"\d{3}-\d{4}"), "call 555-1234 now").passed

    def test_no_match_fails_with_reason(self) -> None:
        result = score(regex(pattern=r"^\d+$"), "abc")
        assert not result.passed
        assert result.reason == "no match for pattern /^\\d+$/"

    def test_full_requires_whole_output(self) -> None:
        assert not score(regex(pattern=r"\d+", full=True), "42 apples").passed
        assert score(regex(pattern=r"\d+", full=True), "42").passed

    def test_ignore_case(self) -> None:
        assert not score(regex(pattern="paris"), "PARIS").passed
        assert score(regex(pattern="paris", ignore_case=True), "PARIS").passed

    def test_pattern_falls_back_to_expected(self) -> None:
        assert score(regex(), "order #123", r"#\d+").passed
        assert not score(regex(), "order", r"#\d+").passed

    def test_param_wins_over_expected(self) -> None:
        assert score(regex(pattern="a"), "a", "zzz").passed

    def test_no_pattern_and_no_expected_fails_with_reason(self) -> None:
        result = score(regex(), "x")
        assert not result.passed
        assert result.reason == "no pattern param and case has no expected value"

    def test_invalid_pattern_param_is_a_config_error(self) -> None:
        with pytest.raises(ScorerConfigError, match="invalid regex pattern '\\('"):
            regex(pattern="(")

    def test_invalid_expected_pattern_fails_the_case(self) -> None:
        result = score(regex(), "x", "(")
        assert not result.passed
        assert result.reason is not None
        assert result.reason.startswith("invalid regex '('")

    def test_multiline_output(self) -> None:
        assert score(regex(pattern=r"^done$"), "line1\ndone").passed is False
        assert score(regex(pattern=r"(?m)^done$"), "line1\ndone").passed
