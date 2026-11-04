"""Build a provider from a :class:`ProviderConfig`."""

from __future__ import annotations

import os
from collections.abc import Mapping

from agentgauge.core.models import ProviderConfig
from agentgauge.providers.base import Provider
from agentgauge.providers.fake import FakeProvider
from agentgauge.providers.openai_compat import DEFAULT_BASE_URL, OpenAICompatProvider

DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"


class ProviderConfigError(ValueError):
    """The provider configuration is incomplete or refers to something missing."""


def build_provider(config: ProviderConfig, env: Mapping[str, str] | None = None) -> Provider:
    """Create the provider described by ``config``.

    The API key is read from the environment variable named by ``api_key_env``.
    If that is set explicitly the variable must exist; if it is left unset,
    ``OPENAI_API_KEY`` is used when present and no key is sent otherwise, which
    suits local servers.
    """
    environ = os.environ if env is None else env
    if config.type == "fake":
        return FakeProvider(
            config.responses,
            params=config.params,
            name=config.model or "fake",
            match=config.match,
        )

    if not config.model:
        raise ProviderConfigError("provider config needs a model")
    if config.api_key_env:
        api_key = environ.get(config.api_key_env)
        if not api_key:
            raise ProviderConfigError(
                f"environment variable {config.api_key_env} is not set (provider api_key_env)"
            )
    else:
        api_key = environ.get(DEFAULT_API_KEY_ENV) or None
    return OpenAICompatProvider(
        config.model,
        base_url=config.base_url or DEFAULT_BASE_URL,
        api_key=api_key,
        params=config.params,
    )
