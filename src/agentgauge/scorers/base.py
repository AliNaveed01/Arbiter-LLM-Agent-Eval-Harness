"""The scorer protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentgauge.core.models import ModelOutput, Score, TestCase


@runtime_checkable
class Scorer(Protocol):
    """Judges one model output against its test case.

    ``score`` is async so that scorers backed by a model (the LLM judge) fit the
    same interface as deterministic ones. A scorer returns a failing ``Score``
    for output it judges wrong, and raises only for problems with the scorer
    itself or its inputs.
    """

    @property
    def name(self) -> str:
        """The registry name, recorded on every ``Score``."""
        ...

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        """Score ``output`` for ``case``."""
        ...
