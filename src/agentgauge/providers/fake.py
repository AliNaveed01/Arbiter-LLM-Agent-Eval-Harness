"""A deterministic in-memory provider for tests and examples."""

from __future__ import annotations

from collections.abc import Mapping

from agentgauge.core.models import ModelOutput


class FakeProvider:
    """Returns canned responses and never touches the network.

    Output is a pure function of the prompt: the same prompt always yields the
    same text, token counts and latency.
    """

    def __init__(
        self,
        responses: Mapping[str, str] | None = None,
        *,
        default: str | None = None,
        errors: Mapping[str, Exception] | None = None,
        latency_ms: float = 0.0,
        name: str = "fake",
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default
        self._errors = dict(errors or {})
        self._latency_ms = latency_ms
        self._name = name
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, prompt: str) -> ModelOutput:
        self.calls.append(prompt)
        if prompt in self._errors:
            raise self._errors[prompt]
        if prompt in self._responses:
            text = self._responses[prompt]
        elif self._default is not None:
            text = self._default
        else:
            raise KeyError(f"FakeProvider has no response for prompt: {prompt!r}")
        return ModelOutput(
            text=text,
            latency_ms=self._latency_ms,
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            cost_usd=0.0,
        )
