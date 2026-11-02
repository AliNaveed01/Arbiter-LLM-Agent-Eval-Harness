"""The provider protocol every model backend implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentgauge.core.models import ModelOutput


@runtime_checkable
class Provider(Protocol):
    """Something that can turn a prompt into a :class:`ModelOutput`."""

    @property
    def name(self) -> str:
        """Stable identifier for the backing model, recorded on runs."""
        ...

    async def complete(self, prompt: str) -> ModelOutput:
        """Run one prompt and return the model's output.

        Implementations raise on failure; callers decide how to record it.
        """
        ...
