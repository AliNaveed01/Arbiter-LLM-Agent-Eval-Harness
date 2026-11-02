import asyncio
import socket

import pytest

from agentgauge.providers import FakeProvider, Provider


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeProvider(default="x"), Provider)


def test_returns_canned_response_with_token_counts() -> None:
    provider = FakeProvider({"2+2?": "it is four"}, latency_ms=5.0)
    out = asyncio.run(provider.complete("2+2?"))
    assert out.text == "it is four"
    assert out.latency_ms == 5.0
    assert out.prompt_tokens == 1
    assert out.completion_tokens == 3
    assert out.cost_usd == 0.0


def test_is_deterministic() -> None:
    provider = FakeProvider(default="same")
    first = asyncio.run(provider.complete("hello"))
    second = asyncio.run(provider.complete("hello"))
    assert first == second


def test_default_used_for_unknown_prompt() -> None:
    out = asyncio.run(FakeProvider({"a": "1"}, default="fallback").complete("b"))
    assert out.text == "fallback"


def test_unknown_prompt_without_default_raises() -> None:
    with pytest.raises(KeyError, match="no response"):
        asyncio.run(FakeProvider({"a": "1"}).complete("b"))


def test_injected_error_is_raised() -> None:
    provider = FakeProvider(default="ok", errors={"boom": TimeoutError("slow")})
    with pytest.raises(TimeoutError):
        asyncio.run(provider.complete("boom"))


def test_records_calls_and_name() -> None:
    provider = FakeProvider(default="ok", name="fake-1")
    asyncio.run(provider.complete("a"))
    asyncio.run(provider.complete("b"))
    assert provider.calls == ["a", "b"]
    assert provider.name == "fake-1"


def test_unit_suite_blocks_network() -> None:
    with pytest.raises(RuntimeError, match="network access"):
        socket.getaddrinfo("example.com", 80)
    with pytest.raises(RuntimeError, match="network access"):
        socket.create_connection(("127.0.0.1", 9))
