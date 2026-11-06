"""Provider for any OpenAI-compatible ``/chat/completions`` endpoint."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from types import TracebackType
from typing import Any, Self, cast

import anyio
import httpx

from agentgauge.core.models import (
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    ToolCall,
    ToolSpec,
)
from agentgauge.providers.base import ProviderError

DEFAULT_BASE_URL = "https://api.openai.com/v1"
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


def to_openai_message(message: Message) -> dict[str, Any]:
    """Convert a :class:`Message` to an OpenAI chat message dict."""
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        out["content"] = message.content or None
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    return out


def from_openai_message(data: Mapping[str, Any]) -> Message:
    """Convert an OpenAI chat message dict to a :class:`Message`."""
    calls: list[ToolCall] = []
    raw_calls = _list(data.get("tool_calls") or [], "tool_calls")
    for raw in raw_calls:
        call = _obj(raw, "tool call")
        function = _obj(call.get("function"), "tool call function")
        arguments: Any = function.get("arguments", "")
        if "id" not in call or "name" not in function:
            raise ProviderError(f"malformed tool call in response: {raw!r}")
        calls.append(
            ToolCall(
                id=str(call["id"]),
                name=str(function["name"]),
                # Some servers return arguments as an object rather than a JSON string.
                arguments=arguments if isinstance(arguments, str) else json.dumps(arguments),
            )
        )
    return Message(
        role=data.get("role", "assistant"),
        content=data.get("content") or "",
        tool_call_id=data.get("tool_call_id"),
        tool_calls=tuple(calls),
    )


def to_openai_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class OpenAICompatProvider:
    """Calls ``{base_url}/chat/completions`` with httpx.

    Transport errors, timeouts and retryable statuses (408, 409, 429, 5xx) are
    retried up to ``max_retries`` times with exponential backoff and full jitter.
    A ``Retry-After`` header (in seconds) raises the wait, up to ``backoff_max``.
    Other 4xx responses fail immediately. Reported latency is that of the
    successful request only, not of earlier failed attempts or waits. ``extra_body`` fields
    are added to every request; they may not replace a field the adapter sets itself.
    """

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        params: GenerationParams | None = None,
        extra_body: Mapping[str, Any] | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_max: float = 8.0,
        input_cost_per_mtok: float | None = None,
        output_cost_per_mtok: float | None = None,
        name: str | None = None,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.default_params = params or GenerationParams()
        self._extra_body = dict(extra_body or {})
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._input_cost = input_cost_per_mtok
        self._output_cost = output_cost_per_mtok
        self._name = name or model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._clock = clock

    @property
    def name(self) -> str:
        return self._name

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def complete(self, request: CompletionRequest) -> ModelOutput:
        payload = self._payload(request)
        for attempt in range(self._max_retries + 1):
            retry_after: float | None = None
            cause: BaseException | None = None
            status: int | None = None
            start = self._clock()
            try:
                response = await self._client.post(self._url, json=payload, headers=self._headers)
            except httpx.TransportError as exc:
                cause = exc
                error = f"{type(exc).__name__}: {exc}"
            else:
                latency_ms = (self._clock() - start) * 1000
                if response.status_code < 400:
                    return self._parse(response, latency_ms)
                status = response.status_code
                error = f"HTTP {status}: {response.text[:200]}"
                if status not in RETRYABLE_STATUS:
                    raise ProviderError(error, status_code=status)
                retry_after = _retry_after(response)
            if attempt == self._max_retries:
                raise ProviderError(
                    f"giving up after {attempt + 1} attempts: {error}", status_code=status
                ) from cause
            await self._sleep(self._delay(attempt, retry_after))
        raise AssertionError("unreachable")  # pragma: no cover

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        cap = min(self._backoff_max, self._backoff_base * 2**attempt)
        delay = self._rng.uniform(0, cap)
        if retry_after is not None:
            delay = max(delay, min(retry_after, self._backoff_max))
        return delay

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        params = (request.params or GenerationParams()).merged_over(self.default_params)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [to_openai_message(m) for m in request.messages],
        }
        if request.tools:
            payload["tools"] = [to_openai_tool(t) for t in request.tools]
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.max_tokens is not None:
            payload["max_tokens"] = params.max_tokens
        if params.seed is not None:
            payload["seed"] = params.seed
        if params.stop is not None:
            payload["stop"] = list(params.stop)
        clashes = sorted(self._extra_body.keys() & payload.keys())
        if clashes:
            raise ProviderError(f"extra_body may not override request fields: {', '.join(clashes)}")
        return {**payload, **self._extra_body}

    def _parse(self, response: httpx.Response, latency_ms: float) -> ModelOutput:
        try:
            body: Any = response.json()
            message = from_openai_message(body["choices"][0]["message"])
        except ProviderError:
            raise
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"malformed response: {response.text[:200]}") from exc
        usage = _obj(body.get("usage") or {}, "usage")
        prompt_tokens = _int(usage.get("prompt_tokens"))
        completion_tokens = _int(usage.get("completion_tokens"))
        return ModelOutput(
            text=message.content,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self._cost(prompt_tokens, completion_tokens),
            tool_calls=message.tool_calls,
            raw=_obj(body, "response"),
        )

    def _cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
        if self._input_cost is None or self._output_cost is None:
            return None
        if prompt_tokens is None or completion_tokens is None:
            return None
        return (prompt_tokens * self._input_cost + completion_tokens * self._output_cost) / 1e6


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # HTTP-date form is not supported; fall back to backoff


def _obj(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderError(f"malformed response: {what} is not an object")
    return cast("dict[str, Any]", value)


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProviderError(f"malformed response: {what} is not a list")
    return cast("list[Any]", value)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
