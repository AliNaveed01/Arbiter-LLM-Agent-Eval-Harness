"""Name-based scorer registry, so suite files can reference scorers by name."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from agentgauge.core.models import ScorerSpec
from agentgauge.scorers.base import Scorer

F = TypeVar("F", bound=Callable[..., Scorer])

_REGISTRY: dict[str, Callable[..., Scorer]] = {}


class ScorerConfigError(ValueError):
    """A scorer name is unknown or its params are invalid."""


def register_scorer(name: str) -> Callable[[F], F]:
    """Class decorator registering a scorer factory under ``name``."""

    def decorator(factory: F) -> F:
        if name in _REGISTRY:
            raise ValueError(f"scorer {name!r} is already registered")
        _REGISTRY[name] = factory
        return factory

    return decorator


def unregister_scorer(name: str) -> None:
    """Remove a registered scorer (mainly for tests and plugins)."""
    _REGISTRY.pop(name, None)


def available_scorers() -> list[str]:
    return sorted(_REGISTRY)


def create_scorer(spec: str | ScorerSpec) -> Scorer:
    """Instantiate the scorer named by ``spec`` with its params."""
    if isinstance(spec, str):
        spec = ScorerSpec(name=spec)
    factory = _REGISTRY.get(spec.name)
    if factory is None:
        known = ", ".join(available_scorers()) or "none registered"
        raise ScorerConfigError(f"unknown scorer {spec.name!r}; available: {known}")
    params: dict[str, Any] = spec.params
    try:
        return factory(**params)
    except TypeError as exc:
        raise ScorerConfigError(f"invalid params for scorer {spec.name!r}: {exc}") from exc
