import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
import respx

from agentgauge.core import (
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    ToolCall,
    ToolSpec,
)
from agentgauge.providers import OpenAICompatProvider, Provider, ProviderError
from agentgauge.providers.openai_compat import (
    from_openai_message,
    to_openai_message,
    to_openai_tool,
)

BASE = "http://llm.test/v1"
URL = f"{BASE}/chat/completions"


def ok_body(content: str | None = "hello", **extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content, **extra}
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3},
    }


def request(text: str = "hi", **kwargs: Any) -> CompletionRequest:
    return CompletionRequest(messages=(Message(role="user", content=text),), **kwargs)


class Sleeps:
    """Records requested sleeps instead of waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class TopOfRange(random.Random):
    """RNG whose ``uniform(0, cap)`` always returns ``cap``."""

    def uniform(self, a: float, b: float) -> float:
        return b


def run(
    req: CompletionRequest,
    *,
    sleeps: Sleeps | None = None,
    **kwargs: Any,
) -> ModelOutput:
    async def go() -> ModelOutput:
        async with OpenAICompatProvider(
            "m", base_url=BASE, sleep=sleeps or Sleeps(), rng=TopOfRange(), **kwargs
        ) as provider:
            return await provider.complete(req)

    return asyncio.run(go())


def sent(route: respx.Route, index: int = -1) -> dict[str, Any]:
    return json.loads(route.calls[index].request.content)


@respx.mock
def test_success_maps_text_tokens_and_raw() -> None:
    route = respx.post(URL).respond(json=ok_body("four"))
    out = run(request("2+2?"))
    assert out.text == "four"
    assert out.prompt_tokens == 11
    assert out.completion_tokens == 3
    assert out.raw == ok_body("four")
    assert sent(route) == {"model": "m", "messages": [{"role": "user", "content": "2+2?"}]}


def test_satisfies_provider_protocol() -> None:
    provider = OpenAICompatProvider("gpt-x", name="custom")
    assert isinstance(provider, Provider)
    assert provider.name == "custom"
    assert OpenAICompatProvider("gpt-x").name == "gpt-x"
    asyncio.run(provider.aclose())


@respx.mock
def test_latency_measured_from_successful_request() -> None:
    respx.post(URL).respond(json=ok_body())
    ticks = iter([10.0, 10.25])
    out = run(request(), clock=lambda: next(ticks))
    assert out.latency_ms == pytest.approx(250.0)


@respx.mock
def test_auth_header_and_trailing_slash_base_url() -> None:
    route = respx.post(URL).respond(json=ok_body())

    async def go() -> None:
        async with OpenAICompatProvider("m", base_url=BASE + "/", api_key="sk-test") as p:
            await p.complete(request())

    asyncio.run(go())
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"


@respx.mock
def test_no_auth_header_without_key() -> None:
    route = respx.post(URL).respond(json=ok_body())
    run(request())
    assert "authorization" not in route.calls[0].request.headers


@respx.mock
def test_params_default_and_override_field_by_field() -> None:
    route = respx.post(URL).respond(json=ok_body())
    defaults = GenerationParams(temperature=0.2, max_tokens=50, seed=7)
    run(request(params=GenerationParams(temperature=0.9, stop=("END",))), params=defaults)
    body = sent(route)
    assert body["temperature"] == 0.9
    assert body["max_tokens"] == 50
    assert body["seed"] == 7
    assert body["stop"] == ["END"]


@respx.mock
def test_unset_params_are_omitted() -> None:
    route = respx.post(URL).respond(json=ok_body())
    run(request())
    assert set(sent(route)) == {"model", "messages"}


@respx.mock
def test_tools_sent_in_openai_format() -> None:
    route = respx.post(URL).respond(json=ok_body())
    tool = ToolSpec(name="search", description="Search", parameters={"type": "object"})
    run(request(tools=(tool,)))
    assert sent(route)["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert to_openai_tool(tool) == sent(route)["tools"][0]


@respx.mock
def test_assistant_tool_calls_and_tool_messages_are_sent_in_openai_format() -> None:
    route = respx.post(URL).respond(json=ok_body())
    call = ToolCall(id="call_1", name="get_weather", arguments='{"city": "Paris"}')
    run(
        CompletionRequest(
            messages=(
                Message(role="user", content="weather?"),
                Message(role="assistant", content="", tool_calls=(call,)),
                Message(role="tool", content='{"temp": 18}', tool_call_id="call_1"),
            )
        )
    )
    assert sent(route)["messages"] == [
        {"role": "user", "content": "weather?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"temp": 18}'},
    ]


@respx.mock
def test_tool_calls_in_response_are_parsed() -> None:
    tool_calls = [
        {"id": "c1", "type": "function", "function": {"name": "a", "arguments": '{"x": 1}'}},
        {"id": "c2", "type": "function", "function": {"name": "b", "arguments": {"y": 2}}},
    ]
    respx.post(URL).respond(json=ok_body(None, tool_calls=tool_calls))
    out = run(request())
    assert out.text == ""
    assert out.tool_calls == (
        ToolCall(id="c1", name="a", arguments='{"x": 1}'),
        ToolCall(id="c2", name="b", arguments='{"y": 2}'),
    )


def test_message_mapping_round_trips() -> None:
    call = ToolCall(id="c1", name="a", arguments="{}")
    messages = [
        Message(role="system", content="s"),
        Message(role="user", content="u"),
        Message(role="assistant", content="", tool_calls=(call,)),
        Message(role="assistant", content="with text", tool_calls=(call,)),
        Message(role="assistant", content="plain"),
        Message(role="tool", content="r", tool_call_id="c1"),
    ]
    for message in messages:
        assert from_openai_message(to_openai_message(message)) == message


@pytest.mark.parametrize(
    "bad",
    [
        {"role": "assistant", "tool_calls": [{"id": "c1"}]},
        {"role": "assistant", "tool_calls": [{"function": {"name": "a"}}]},
        {"role": "assistant", "tool_calls": ["nope"]},
        {"role": "assistant", "tool_calls": "nope"},
    ],
)
def test_malformed_tool_calls_raise(bad: dict[str, Any]) -> None:
    with pytest.raises(ProviderError, match="malformed"):
        from_openai_message(bad)


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"nope": 1}),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "tool_calls": 5}}]}
        ),
        httpx.Response(200, json={**ok_body(), "usage": 5}),
    ],
)
def test_malformed_response_raises(response: httpx.Response) -> None:
    respx.post(URL).mock(return_value=response)
    with pytest.raises(ProviderError, match="malformed"):
        run(request())


@respx.mock
def test_missing_usage_gives_none_tokens() -> None:
    body = ok_body()
    del body["usage"]
    respx.post(URL).respond(json=body)
    out = run(request(), input_cost_per_mtok=1.0, output_cost_per_mtok=2.0)
    assert out.prompt_tokens is None
    assert out.completion_tokens is None
    assert out.cost_usd is None


@respx.mock
def test_non_integer_token_counts_are_ignored() -> None:
    body = ok_body()
    body["usage"] = {"prompt_tokens": True, "completion_tokens": "3"}
    respx.post(URL).respond(json=body)
    out = run(request())
    assert out.prompt_tokens is None
    assert out.completion_tokens is None


@respx.mock
def test_cost_computed_from_prices() -> None:
    respx.post(URL).respond(json=ok_body())
    out = run(request(), input_cost_per_mtok=1.0, output_cost_per_mtok=2.0)
    assert out.cost_usd == pytest.approx((11 * 1.0 + 3 * 2.0) / 1e6)


@respx.mock
def test_cost_is_none_without_prices() -> None:
    respx.post(URL).respond(json=ok_body())
    assert run(request()).cost_usd is None


@respx.mock
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503])
def test_retries_retryable_status_then_succeeds(status: int) -> None:
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(status), httpx.Response(200, json=ok_body("done"))]
    )
    sleeps = Sleeps()
    out = run(request(), sleeps=sleeps)
    assert out.text == "done"
    assert route.call_count == 2
    assert len(sleeps.calls) == 1


@respx.mock
def test_retries_timeouts_and_connection_errors() -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            httpx.ConnectError("refused"),
            httpx.Response(200, json=ok_body("finally")),
        ]
    )
    out = run(request())
    assert out.text == "finally"
    assert route.call_count == 3


@respx.mock
def test_backoff_is_exponential_and_capped() -> None:
    respx.post(URL).mock(return_value=httpx.Response(503))
    sleeps = Sleeps()
    with pytest.raises(ProviderError):
        run(request(), sleeps=sleeps, max_retries=5, backoff_base=1.0, backoff_max=5.0)
    # TopOfRange returns the cap: 1, 2, 4, then capped at 5.
    assert sleeps.calls == [1.0, 2.0, 4.0, 5.0, 5.0]


def test_default_rng_jitter_stays_within_cap() -> None:
    provider = OpenAICompatProvider("m", backoff_base=0.5, backoff_max=8.0)
    delays = [provider._delay(2, None) for _ in range(200)]  # pyright: ignore[reportPrivateUsage]
    assert all(0 <= d <= 2.0 for d in delays)
    assert len(set(delays)) > 1
    asyncio.run(provider.aclose())


@respx.mock
def test_retry_after_raises_the_wait_but_is_capped() -> None:
    respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "3"}),
            httpx.Response(429, headers={"retry-after": "999"}),
            httpx.Response(429, headers={"retry-after": "soon"}),
            httpx.Response(200, json=ok_body()),
        ]
    )
    sleeps = Sleeps()
    run(request(), sleeps=sleeps, backoff_base=0.1, backoff_max=10.0)
    assert sleeps.calls == [3.0, 10.0, pytest.approx(0.4)]


@respx.mock
def test_gives_up_after_max_retries() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(ProviderError, match="giving up after 3 attempts") as info:
        run(request(), max_retries=2)
    assert info.value.status_code == 500
    assert "boom" in str(info.value)
    assert route.call_count == 3


@respx.mock
def test_gives_up_on_persistent_timeouts() -> None:
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError, match="ReadTimeout") as info:
        run(request(), max_retries=1)
    assert isinstance(info.value.__cause__, httpx.ReadTimeout)
    assert info.value.status_code is None


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_client_errors_are_not_retried(status: int) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(status, text="nope"))
    sleeps = Sleeps()
    with pytest.raises(ProviderError) as info:
        run(request(), sleeps=sleeps)
    assert info.value.status_code == status
    assert route.call_count == 1
    assert sleeps.calls == []


@respx.mock
def test_max_retries_zero_makes_one_attempt() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderError, match="1 attempts"):
        run(request(), max_retries=0)
    assert route.call_count == 1


@respx.mock
def test_injected_client_is_not_closed() -> None:
    respx.post(URL).respond(json=ok_body())

    async def go() -> bool:
        client = httpx.AsyncClient()
        async with OpenAICompatProvider("m", base_url=BASE, client=client) as provider:
            await provider.complete(request())
        closed = client.is_closed
        await client.aclose()
        return closed

    assert asyncio.run(go()) is False


@respx.mock
def test_owned_client_is_closed_on_exit() -> None:
    respx.post(URL).respond(json=ok_body())
    holder: list[OpenAICompatProvider] = []

    async def go() -> None:
        async with OpenAICompatProvider("m", base_url=BASE) as provider:
            holder.append(provider)
            await provider.complete(request())

    asyncio.run(go())
    assert holder[0]._client.is_closed  # pyright: ignore[reportPrivateUsage]


def test_real_sleep_default_is_anyio() -> None:
    import anyio

    provider = OpenAICompatProvider("m")
    sleep: Callable[[float], Awaitable[None]] = provider._sleep  # pyright: ignore[reportPrivateUsage]
    assert sleep is anyio.sleep
    asyncio.run(provider.aclose())
