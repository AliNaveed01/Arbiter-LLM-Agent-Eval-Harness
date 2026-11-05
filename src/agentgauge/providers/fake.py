"""A deterministic in-memory provider for tests and examples."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

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


Reply = str | FakeResponse


class FakeProvider:
    """Returns canned responses and never touches the network.

    Responses are matched on the content of the last user message. With the
    default ``match="exact"`` a key must equal that content. With
    ``match="contains"`` a key matches when it appears anywhere in it, and the
    first matching key (in insertion order) wins; this suits long, generated
    prompts such as a judge's. A response may be a list: in an agent run the n-th item
    answers the n-th step (counted by the assistant messages after the last user message,
    the last item repeating), so a script of tool calls then an answer is still a pure
    function of the request. Output is a pure function of the request, so the
    same request always yields the same result.
    """

    def __init__(
        self,
        responses: Mapping[str, Reply | Sequence[Reply]] | None = None,
        *,
        default: Reply | None = None,
        errors: Mapping[str, Exception] | None = None,
        params: GenerationParams | None = None,
        latency_ms: float = 0.0,
        name: str = "fake",
        match: Literal["exact", "contains"] = "exact",
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default
        self._errors = dict(errors or {})
        self._latency_ms = latency_ms
        self._match = match
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
        error = self._lookup(self._errors, key)
        if error is not None:
            raise error
        response = self._lookup(self._responses, key)
        if response is None:
            if self._default is None:
                raise KeyError(f"FakeProvider has no response for user message: {key!r}")
            response = self._default
        if not isinstance(response, str | FakeResponse):
            steps = _steps_taken(request.messages)
            response = response[min(steps, len(response) - 1)]
        if isinstance(response, str):
            response = FakeResponse(text=response)
        return ModelOutput(
            text=response.text,
            latency_ms=self._latency_ms,
            prompt_tokens=sum(_count_tokens(m) for m in request.messages),
            completion_tokens=len(response.text.split()),
            cost_usd=0.0,
            tool_calls=response.tool_calls,
        )

    def _lookup[V](self, table: Mapping[str, V], key: str) -> V | None:
        if self._match == "exact":
            return table.get(key)
        return next((value for pattern, value in table.items() if pattern in key), None)


def _steps_taken(messages: tuple[Message, ...]) -> int:
    """How many assistant messages follow the last user message."""
    steps = 0
    for message in reversed(messages):
        if message.role == "user":
            break
        if message.role == "assistant":
            steps += 1
    return steps


def _last_user_content(messages: tuple[Message, ...]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    raise ValueError("request has no user message")


def _count_tokens(message: Message) -> int:
    """Whitespace word count over content plus any tool-call names and arguments."""
    calls = sum(len(c.name.split()) + len(c.arguments.split()) for c in message.tool_calls)
    return len(message.content.split()) + calls
