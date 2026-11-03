"""Deterministic scorers: no model calls, same input gives the same score."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from agentgauge.core.models import ModelOutput, Score, TestCase
from agentgauge.scorers import schema as json_schema
from agentgauge.scorers.registry import ScorerConfigError, register_scorer


def _verdict(name: str, passed: bool, reason: str | None = None) -> Score:
    return Score(scorer=name, value=1.0 if passed else 0.0, passed=passed, reason=reason)


def _missing_expected(name: str) -> Score:
    return _verdict(name, False, "case has no expected value")


@register_scorer("exact_match")
class ExactMatch:
    """Output equals ``case.expected``, optionally ignoring case and edge whitespace."""

    name = "exact_match"

    def __init__(self, case_sensitive: bool = True, strip: bool = True) -> None:
        self._case_sensitive = case_sensitive
        self._strip = strip

    def _normalise(self, text: str) -> str:
        text = text.strip() if self._strip else text
        return text if self._case_sensitive else text.casefold()

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        if case.expected is None:
            return _missing_expected(self.name)
        passed = self._normalise(output.text) == self._normalise(case.expected)
        return _verdict(self.name, passed, None if passed else f"expected {case.expected!r}")


@register_scorer("contains")
class Contains:
    """Output contains ``case.expected`` as a substring."""

    name = "contains"

    def __init__(self, case_sensitive: bool = True) -> None:
        self._case_sensitive = case_sensitive

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        if case.expected is None:
            return _missing_expected(self.name)
        text, needle = output.text, case.expected
        if not self._case_sensitive:
            text, needle = text.casefold(), needle.casefold()
        passed = needle in text
        reason = None if passed else f"output does not contain {case.expected!r}"
        return _verdict(self.name, passed, reason)


@register_scorer("regex")
class Regex:
    """Output matches a regular expression.

    The pattern is the ``pattern`` param, or ``case.expected`` when no param is
    given, so a suite can use one pattern for all cases or one per case. By
    default the pattern may match anywhere in the output (``re.search``); set
    ``full=True`` to require the whole output to match.
    """

    name = "regex"

    def __init__(
        self, pattern: str | None = None, ignore_case: bool = False, full: bool = False
    ) -> None:
        self._flags = re.IGNORECASE if ignore_case else 0
        self._full = full
        try:
            self._fixed = self._compile(pattern) if pattern is not None else None
        except re.error as exc:
            raise ScorerConfigError(f"invalid regex pattern {pattern!r}: {exc}") from exc

    def _compile(self, pattern: str) -> re.Pattern[str]:
        return re.compile(pattern, self._flags)

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        compiled = self._fixed
        if compiled is None:
            if case.expected is None:
                return _verdict(self.name, False, "no pattern param and case has no expected value")
            try:
                compiled = self._compile(case.expected)
            except re.error as exc:
                return _verdict(self.name, False, f"invalid regex {case.expected!r}: {exc}")
        match = compiled.fullmatch(output.text) if self._full else compiled.search(output.text)
        passed = match is not None
        return _verdict(
            self.name, passed, None if passed else f"no match for pattern /{compiled.pattern}/"
        )


_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _parse_number(text: str) -> float | None:
    """The first finite number in ``text``, tolerating thousands separators."""
    cleaned = _THOUSANDS.sub("", text.replace("\u2212", "-"))
    match = _NUMBER.search(cleaned)
    if match is None:
        return None
    value = float(match.group())
    return value if math.isfinite(value) else None


@register_scorer("numeric_tolerance")
class NumericTolerance:
    """First number in the output is within tolerance of the number in ``case.expected``.

    Passes when ``|actual - expected| <= max(abs_tol, rel_tol * |expected|)``.
    With both tolerances at 0 (the default) the numbers must be equal.
    """

    name = "numeric_tolerance"

    def __init__(self, abs_tol: float = 0.0, rel_tol: float = 0.0) -> None:
        for label, value in (("abs_tol", abs_tol), ("rel_tol", rel_tol)):
            if not math.isfinite(value) or value < 0:
                raise ScorerConfigError(f"{label} must be a non-negative number, got {value!r}")
        self._abs_tol = abs_tol
        self._rel_tol = rel_tol

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        if case.expected is None:
            return _missing_expected(self.name)
        expected = _parse_number(case.expected)
        if expected is None:
            return _verdict(self.name, False, f"expected value {case.expected!r} is not numeric")
        actual = _parse_number(output.text)
        if actual is None:
            return _verdict(self.name, False, "no number found in output")
        limit = max(self._abs_tol, self._rel_tol * abs(expected))
        passed = abs(actual - expected) <= limit
        reason = None if passed else f"{actual:g} is not within {limit:g} of {expected:g}"
        return _verdict(self.name, passed, reason)


_FENCE = re.compile(r"^```[A-Za-z0-9_-]*[ \t]*\n(.*?)\n?```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Unwrap a single Markdown code fence, which models often put around JSON."""
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


@register_scorer("json_schema")
class JsonSchema:
    """Output is valid JSON that satisfies the ``schema`` param.

    A single surrounding Markdown code fence is ignored. Only the JSON Schema
    subset documented in :mod:`agentgauge.scorers.schema` is supported; a schema
    using anything else is rejected when the scorer is created.
    """

    name = "json_schema"

    def __init__(self, schema: dict[str, Any]) -> None:
        try:
            json_schema.check_schema(schema)
        except json_schema.SchemaError as exc:
            raise ScorerConfigError(f"invalid json_schema schema: {exc}") from exc
        self._schema = schema

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        try:
            instance: Any = json.loads(_strip_code_fence(output.text))
        except json.JSONDecodeError as exc:
            return _verdict(self.name, False, f"output is not valid JSON: {exc.msg}")
        errors = json_schema.validate(instance, self._schema)
        if not errors:
            return _verdict(self.name, True)
        extra = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
        return _verdict(self.name, False, errors[0] + extra)
