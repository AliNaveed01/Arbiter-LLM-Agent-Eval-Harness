import asyncio
import socket

import pytest

from agentgauge.core import CompletionRequest, GenerationParams, Message, ToolCall
from agentgauge.providers import FakeProvider, FakeResponse, Provider


def req(text: str, **kwargs: object) -> CompletionRequest:
    return CompletionRequest(messages=(Message(role="user", content=text),), **kwargs)  # pyright: ignore[reportArgumentType]


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeProvider(default="x"), Provider)


def test_returns_canned_response_with_token_counts() -> None:
    provider = FakeProvider({"2+2?": "it is four"}, latency_ms=5.0)
    out = asyncio.run(provider.complete(req("2+2?")))
    assert out.text == "it is four"
    assert out.latency_ms == 5.0
    assert out.prompt_tokens == 1
    assert out.completion_tokens == 3
    assert out.cost_usd == 0.0
    assert out.tool_calls == ()


def test_matches_on_last_user_message() -> None:
    provider = FakeProvider({"second": "B", "first": "A"})
    request = CompletionRequest(
        messages=(
            Message(role="system", content="be brief"),
            Message(role="user", content="first"),
            Message(role="assistant", content="A"),
            Message(role="user", content="second"),
            Message(role="tool", content="ignored", tool_call_id="t1"),
        )
    )
    assert asyncio.run(provider.complete(request)).text == "B"
    assert asyncio.run(provider.complete(request)).prompt_tokens == 6


def test_request_without_user_message_raises() -> None:
    request = CompletionRequest(messages=(Message(role="system", content="x"),))
    with pytest.raises(ValueError, match="no user message"):
        asyncio.run(FakeProvider(default="x").complete(request))


def test_canned_tool_calls() -> None:
    call = ToolCall(id="c1", name="search", arguments='{"q": "weather"}')
    provider = FakeProvider({"weather?": FakeResponse(tool_calls=(call,))})
    out = asyncio.run(provider.complete(req("weather?")))
    assert out.tool_calls == (call,)
    assert out.text == ""
    assert out.completion_tokens == 0


def test_is_deterministic() -> None:
    provider = FakeProvider(default="same")
    first = asyncio.run(provider.complete(req("hello")))
    second = asyncio.run(provider.complete(req("hello")))
    assert first == second


def test_default_used_for_unknown_message() -> None:
    out = asyncio.run(FakeProvider({"a": "1"}, default="fallback").complete(req("b")))
    assert out.text == "fallback"


def test_default_can_be_a_response_object() -> None:
    call = ToolCall(id="c1", name="t", arguments="{}")
    provider = FakeProvider(default=FakeResponse(text="x", tool_calls=(call,)))
    out = asyncio.run(provider.complete(req("anything")))
    assert out.tool_calls == (call,)


def test_unknown_message_without_default_raises() -> None:
    with pytest.raises(KeyError, match="no response"):
        asyncio.run(FakeProvider({"a": "1"}).complete(req("b")))


def test_injected_error_is_raised() -> None:
    provider = FakeProvider(default="ok", errors={"boom": TimeoutError("slow")})
    with pytest.raises(TimeoutError):
        asyncio.run(provider.complete(req("boom")))


def test_records_calls_and_name() -> None:
    provider = FakeProvider(default="ok", name="fake-1")
    a, b = req("a"), req("b")
    asyncio.run(provider.complete(a))
    asyncio.run(provider.complete(b))
    assert provider.calls == [a, b]
    assert provider.name == "fake-1"


def test_request_params_override_defaults_field_by_field() -> None:
    provider = FakeProvider(
        default="ok", params=GenerationParams(temperature=0.2, max_tokens=100, seed=7)
    )
    asyncio.run(
        provider.complete(req("a", params=GenerationParams(temperature=0.9, stop=("END",))))
    )
    asyncio.run(provider.complete(req("b")))
    assert provider.effective_params[0] == GenerationParams(
        temperature=0.9, max_tokens=100, seed=7, stop=("END",)
    )
    assert provider.effective_params[1] == provider.default_params


def test_unit_suite_blocks_network() -> None:
    with pytest.raises(RuntimeError, match="network access"):
        socket.getaddrinfo("example.com", 80)
    with pytest.raises(RuntimeError, match="network access"):
        socket.create_connection(("127.0.0.1", 9))


def test_prompt_tokens_count_assistant_tool_calls() -> None:
    call = ToolCall(id="c1", name="web_search", arguments='{"q": "rain today"}')
    request = CompletionRequest(
        messages=(
            Message(role="user", content="weather now"),
            Message(role="assistant", content="", tool_calls=(call,)),
            Message(role="tool", content="sunny", tool_call_id="c1"),
        )
    )
    out = asyncio.run(FakeProvider({"weather now": "sunny"}).complete(request))
    # "weather now" (2) + call name (1) + arguments (3) + "sunny" (1)
    assert out.prompt_tokens == 7


def test_contains_matching_uses_the_first_matching_key() -> None:
    provider = FakeProvider(
        {"Paris": "right", "answer": "generic"}, match="contains", default="none"
    )

    def ask(text: str) -> str:
        request = CompletionRequest(messages=(Message(role="user", content=text),))
        return asyncio.run(provider.complete(request)).text

    assert ask("The answer is Paris, I think") == "right"
    assert ask("just an answer") == "generic"
    assert ask("nothing relevant") == "none"


def test_contains_matching_applies_to_errors_and_exact_stays_the_default() -> None:
    boom = RuntimeError("boom")
    provider = FakeProvider({"x": "ok"}, errors={"bad": boom}, match="contains")
    bad_day = CompletionRequest(messages=(Message(role="user", content="a bad day"),))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(provider.complete(bad_day))
    exact = FakeProvider({"x": "ok"})
    with pytest.raises(KeyError):
        asyncio.run(
            exact.complete(CompletionRequest(messages=(Message(role="user", content="xx"),)))
        )
