"""Deterministic scorers: no model calls, same input gives the same score."""

from __future__ import annotations

from agentgauge.core.models import ModelOutput, Score, TestCase
from agentgauge.scorers.registry import register_scorer


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
