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


def numeric(**params: object) -> Scorer:
    return create_scorer(ScorerSpec(name="numeric_tolerance", params=dict(params)))


class TestNumericTolerance:
    def test_equal_numbers_pass_with_default_tolerance(self) -> None:
        assert score(numeric(), "4", "4").passed
        assert score(numeric(), "4.0", "4").passed

    def test_different_numbers_fail_with_reason(self) -> None:
        result = score(numeric(), "5", "4")
        assert not result.passed
        assert result.reason == "5 is not within 0 of 4"

    def test_absolute_tolerance(self) -> None:
        assert score(numeric(abs_tol=0.01), "3.14", "3.1415").passed
        assert not score(numeric(abs_tol=0.001), "3.14", "3.1415").passed

    def test_relative_tolerance(self) -> None:
        assert score(numeric(rel_tol=0.05), "104", "100").passed
        assert not score(numeric(rel_tol=0.05), "106", "100").passed

    def test_larger_of_the_two_tolerances_applies(self) -> None:
        assert score(numeric(abs_tol=10, rel_tol=0.01), "105", "100").passed
        assert score(numeric(abs_tol=0.1, rel_tol=0.5), "140", "100").passed

    def test_boundary_is_inclusive(self) -> None:
        assert score(numeric(abs_tol=0.5), "4.5", "4").passed

    def test_number_extracted_from_sentence(self) -> None:
        assert score(numeric(), "The answer is 42.", "42").passed

    def test_first_number_is_used(self) -> None:
        assert not score(numeric(), "7 apples and 42 pears", "42").passed

    def test_negative_and_unicode_minus(self) -> None:
        assert score(numeric(), "-3.5", "-3.5").passed
        assert score(numeric(), "\N{MINUS SIGN}3.5", "-3.5").passed

    def test_scientific_notation(self) -> None:
        assert score(numeric(rel_tol=1e-6), "1.5e3", "1500").passed

    def test_thousands_separators_and_currency(self) -> None:
        assert score(numeric(), "$1,234,567.50", "1234567.5").passed

    def test_comma_between_numbers_is_not_a_thousands_separator(self) -> None:
        assert score(numeric(), "1,2", "1").passed

    def test_leading_decimal_point(self) -> None:
        assert score(numeric(), ".5", "0.5").passed

    def test_zero_expected_with_relative_tolerance_only_matches_zero(self) -> None:
        assert score(numeric(rel_tol=0.5), "0", "0").passed
        assert not score(numeric(rel_tol=0.5), "0.1", "0").passed

    def test_no_number_in_output(self) -> None:
        result = score(numeric(), "forty-two", "42")
        assert (result.passed, result.reason) == (False, "no number found in output")

    def test_non_finite_output_is_not_a_number(self) -> None:
        assert score(numeric(), "1e999", "1").reason == "no number found in output"

    def test_non_numeric_expected(self) -> None:
        result = score(numeric(), "42", "forty-two")
        assert result.reason == "expected value 'forty-two' is not numeric"

    def test_missing_expected(self) -> None:
        assert score(numeric(), "42").reason == "case has no expected value"

    @pytest.mark.parametrize(
        "params", [{"abs_tol": -1}, {"rel_tol": -0.1}, {"abs_tol": float("nan")}]
    )
    def test_invalid_tolerances_are_config_errors(self, params: dict[str, float]) -> None:
        with pytest.raises(ScorerConfigError, match="non-negative"):
            numeric(**params)


SCHEMA = {
    "type": "object",
    "required": ["name", "age"],
    "properties": {"name": {"type": "string"}, "age": {"type": "integer", "minimum": 0}},
}


def json_scorer(schema: dict[str, object] = SCHEMA) -> Scorer:
    return create_scorer(ScorerSpec(name="json_schema", params={"schema": schema}))


class TestJsonSchema:
    def test_valid_json_passes(self) -> None:
        result = score(json_scorer(), '{"name": "Ada", "age": 36}')
        assert (result.scorer, result.value, result.passed, result.reason) == (
            "json_schema",
            1.0,
            True,
            None,
        )

    def test_schema_violation_fails_with_first_error(self) -> None:
        result = score(json_scorer(), '{"name": "Ada", "age": "old"}')
        assert not result.passed
        assert result.reason == "$.age: expected integer, got string"

    def test_reason_counts_additional_errors(self) -> None:
        result = score(json_scorer(), '{"age": -1}')
        assert result.reason == "$: missing required property 'name' (+1 more)"

    def test_invalid_json_fails_with_reason(self) -> None:
        result = score(json_scorer(), '{"name": ')
        assert not result.passed
        assert result.reason is not None
        assert result.reason.startswith("output is not valid JSON")

    def test_empty_output_is_invalid_json(self) -> None:
        assert not score(json_scorer(), "").passed

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert score(json_scorer(), '\n  {"name": "Ada", "age": 1}\n').passed

    @pytest.mark.parametrize(
        "fence", ["```json\n{body}\n```", "```\n{body}\n```", "```JSON\n{body}```"]
    )
    def test_code_fence_is_stripped(self, fence: str) -> None:
        text = fence.replace("{body}", '{"name": "Ada", "age": 1}')
        assert score(json_scorer(), f"  {text}  ").passed

    def test_prose_around_json_is_not_valid(self) -> None:
        assert not score(json_scorer(), 'Here: {"name": "Ada", "age": 1}').passed

    def test_non_object_json_against_object_schema(self) -> None:
        result = score(json_scorer(), "[1, 2]")
        assert result.reason == "$: expected object, got array"

    def test_scalar_schema(self) -> None:
        assert score(json_scorer({"type": "integer"}), "42").passed
        assert not score(json_scorer({"type": "integer"}), "4.5").passed

    def test_unsupported_keyword_is_a_config_error(self) -> None:
        with pytest.raises(ScorerConfigError, match="unsupported keyword '\\$ref'"):
            json_scorer({"$ref": "#/defs/x"})

    def test_missing_schema_param_is_a_config_error(self) -> None:
        with pytest.raises(ScorerConfigError, match="invalid params"):
            create_scorer("json_schema")
