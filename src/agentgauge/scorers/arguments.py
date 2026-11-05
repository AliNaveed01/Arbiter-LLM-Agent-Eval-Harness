"""Comparing tool-call arguments: strings ignore case and edge whitespace, the rest is exact."""

from __future__ import annotations

import json
from typing import Any


def normalise(value: Any) -> Any:
    """A comparison form of ``value`` with strings casefolded and stripped, recursively."""
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, list):
        items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        return [normalise(item) for item in items]
    if isinstance(value, dict):
        mapping: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
        return {key: normalise(item) for key, item in mapping.items()}
    return value


def same_arguments(left: Any, right: Any) -> bool:
    """Whether two decoded argument values are equal under :func:`normalise`."""
    return normalise(left) == normalise(right)


def parse_arguments(text: str) -> dict[str, Any] | None:
    """Decode a tool call's argument string; ``None`` unless it is a JSON object."""
    try:
        value: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value  # pyright: ignore[reportUnknownVariableType]
