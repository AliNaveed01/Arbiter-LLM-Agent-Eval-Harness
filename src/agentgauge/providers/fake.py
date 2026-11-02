"""A deterministic in-memory provider for tests and examples."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agentgauge.core.models import (
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    ToolCall,
)


@dataclass(frozen=True)
class FakeResponse:
    """A canned response: text, tool calls, or both."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class FakeProvider:
    """Returns canned responses and never touches the network.

    Responses are matched on the content of the last user message. Output is a
    pure function of the request, so the same request always yields the same
    result.
    """

    def __init__(
        self,
        responses: Mapping[str, str | FakeResponse] | None = None,
        *,
        default: str | FakeResponse | None = None,
        errors: Mapping[str, Exception] | None = None,
        params: GenerationParams | None = None,
        latency_ms: float = 0.0,
        name: str = "fake",
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default
        self._errors = dict(errors or {})
        self._latency_ms = latency_ms
        self._name = name
        self.default_params = params or GenerationParams()
        self.calls: list[CompletionRequest] = []
        self.effective_params: list[GenerationParams] = []

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: CompletionRequest) -> ModelOutput:
        self.calls.append(request)
        self.effective_params.append(
            (request.params or GenerationParams()).merged_over(self.default_params)
        )
        key = _last_user_content(request.messages)
        if key in self._errors:
            raise self._errors[key]
        if key in self._responses:
            response = self._responses[key]
        elif self._default is not None:
            response = self._default
        else:
            raise KeyError(f"FakeProvider has no response for user message: {key!r}")
        if isinstance(response, str):
            response = FakeResponse(text=response)
        return ModelOutput(
            text=response.text,
            latency_ms=self._latency_ms,
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=len(response.text.split()),
            cost_usd=0.0,
            tool_calls=response.tool_calls,
        )


def _last_user_content(messages: tuple[Message, ...]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    raise ValueError("request has no user message")
