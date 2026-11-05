import asyncio

import pytest

from agentgauge.core import CompletionRequest, GenerationParams, Message, ProviderConfig
from agentgauge.providers import (
    FakeProvider,
    OpenAICompatProvider,
    ProviderConfigError,
    build_provider,
)
from agentgauge.providers.openai_compat import DEFAULT_BASE_URL


def request(text: str) -> CompletionRequest:
    return CompletionRequest(messages=(Message(role="user", content=text),))


def test_fake_provider_uses_responses_params_and_model_as_name() -> None:
    config = ProviderConfig(
        type="fake", model="scripted", responses={"hi": "hello"}, params=GenerationParams(seed=1)
    )
    provider = build_provider(config, env={})
    assert isinstance(provider, FakeProvider)
    assert provider.name == "scripted"
    assert provider.default_params == GenerationParams(seed=1)
    assert asyncio.run(provider.complete(request("hi"))).text == "hello"


def test_fake_provider_defaults_its_name() -> None:
    assert build_provider(ProviderConfig(type="fake"), env={}).name == "fake"


def test_openai_compat_provider_is_configured() -> None:
    config = ProviderConfig(
        type="openai_compat",
        model="gpt-x",
        base_url="http://localhost:8000/v1",
        api_key_env="MY_KEY",
        params=GenerationParams(temperature=0),
    )
    provider = build_provider(config, env={"MY_KEY": "sk-1"})
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.name == "gpt-x"
    assert provider.default_params == GenerationParams(temperature=0)
    assert provider._url == "http://localhost:8000/v1/chat/completions"  # pyright: ignore[reportPrivateUsage]
    assert provider._headers == {"Authorization": "Bearer sk-1"}  # pyright: ignore[reportPrivateUsage]
    asyncio.run(provider.aclose())


def test_base_url_defaults_to_openai() -> None:
    provider = build_provider(ProviderConfig(type="openai_compat", model="m"), env={})
    assert isinstance(provider, OpenAICompatProvider)
    assert provider._url == f"{DEFAULT_BASE_URL}/chat/completions"  # pyright: ignore[reportPrivateUsage]
    asyncio.run(provider.aclose())


def test_default_key_env_is_used_when_present_and_optional_when_absent() -> None:
    config = ProviderConfig(type="openai_compat", model="m")
    with_key = build_provider(config, env={"OPENAI_API_KEY": "sk-default"})
    without_key = build_provider(config, env={})
    assert isinstance(with_key, OpenAICompatProvider)
    assert isinstance(without_key, OpenAICompatProvider)
    assert with_key._headers == {"Authorization": "Bearer sk-default"}  # pyright: ignore[reportPrivateUsage]
    assert without_key._headers == {}  # pyright: ignore[reportPrivateUsage]
    asyncio.run(with_key.aclose())
    asyncio.run(without_key.aclose())


def test_empty_default_key_counts_as_absent() -> None:
    provider = build_provider(
        ProviderConfig(type="openai_compat", model="m"), env={"OPENAI_API_KEY": ""}
    )
    assert isinstance(provider, OpenAICompatProvider)
    assert provider._headers == {}  # pyright: ignore[reportPrivateUsage]
    asyncio.run(provider.aclose())


def test_explicit_key_env_must_be_set() -> None:
    config = ProviderConfig(type="openai_compat", model="m", api_key_env="MY_KEY")
    with pytest.raises(ProviderConfigError, match="MY_KEY is not set"):
        build_provider(config, env={"OPENAI_API_KEY": "sk-other"})
    with pytest.raises(ProviderConfigError, match="MY_KEY is not set"):
        build_provider(config, env={"MY_KEY": ""})


def test_openai_compat_requires_a_model() -> None:
    with pytest.raises(ProviderConfigError, match="needs a model"):
        build_provider(ProviderConfig(type="openai_compat"), env={})


def test_real_environment_is_used_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AG_TEST_KEY", "sk-from-env")
    config = ProviderConfig(type="openai_compat", model="m", api_key_env="AG_TEST_KEY")
    provider = build_provider(config)
    assert isinstance(provider, OpenAICompatProvider)
    assert provider._headers == {"Authorization": "Bearer sk-from-env"}  # pyright: ignore[reportPrivateUsage]
    asyncio.run(provider.aclose())


def test_fake_provider_match_mode_comes_from_the_config() -> None:
    config = ProviderConfig(type="fake", responses={"cat": "meow"}, match="contains")
    provider = build_provider(config)
    request = CompletionRequest(messages=(Message(role="user", content="a cat sat"),))
    assert asyncio.run(provider.complete(request)).text == "meow"


def test_fake_config_scripts_tool_calls_with_mapping_or_string_arguments() -> None:
    config = ProviderConfig.model_validate(
        {
            "type": "fake",
            "responses": {
                "q": [
                    {"tool_calls": [{"name": "search", "arguments": {"q": "cats"}}]},
                    {"tool_calls": [{"name": "open", "arguments": '{"id": 7}'}, {"name": "ping"}]},
                    {"text": "found it"},
                    "plain string",
                ]
            },
        }
    )
    provider = build_provider(config)
    user = Message(role="user", content="q")
    assistant = Message(role="assistant", content="")

    def step(n: int) -> tuple[Message, ...]:
        return (user, *([assistant] * n))

    first = asyncio.run(provider.complete(CompletionRequest(messages=step(0))))
    second = asyncio.run(provider.complete(CompletionRequest(messages=step(1))))
    third = asyncio.run(provider.complete(CompletionRequest(messages=step(2))))
    fourth = asyncio.run(provider.complete(CompletionRequest(messages=step(3))))
    assert [(c.name, c.arguments) for c in first.tool_calls] == [("search", '{"q": "cats"}')]
    assert [(c.id, c.name, c.arguments) for c in second.tool_calls] == [
        ("call_1", "open", '{"id": 7}'),
        ("call_2", "ping", "{}"),
    ]
    assert (third.text, fourth.text) == ("found it", "plain string")
