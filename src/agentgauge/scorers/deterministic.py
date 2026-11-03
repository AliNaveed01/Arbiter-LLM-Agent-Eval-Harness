"""Deterministic scorers: no model calls, same input gives the same score."""

from __future__ import annotations

import re

from agentgauge.core.models import ModelOutput, Score, TestCase
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
