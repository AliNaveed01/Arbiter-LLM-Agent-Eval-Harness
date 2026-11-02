"""The provider protocol every model backend implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentgauge.core.models import CompletionRequest, ModelOutput


class ProviderError(Exception):
    """A provider failed to produce an output (after any retries)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@runtime_checkable
class Provider(Protocol):
    """Something that can turn a :class:`CompletionRequest` into a :class:`ModelOutput`.

    A provider holds default ``GenerationParams``. Params on a request override
    them field by field (see ``GenerationParams.merged_over``).
    """

    @property
    def name(self) -> str:
        """Stable identifier for the backing model, recorded on runs."""
        ...

    async def complete(self, request: CompletionRequest) -> ModelOutput:
        """Run one request and return the model's output.

        Implementations raise on failure; callers decide how to record it.
        """
        ...
