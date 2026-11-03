"""A small JSON Schema validator covering the subset agentgauge needs.

Supported keywords: ``type``, ``enum``, ``const``, ``properties``, ``required``,
``additionalProperties`` (boolean or schema), ``items``, ``minItems``,
``maxItems``, ``minLength``, ``maxLength``, ``pattern``, ``minimum``,
``maximum`` and ``anyOf``. Annotation keywords (``title``, ``description``,
``default``, ``examples``, ``$schema``, ``$id``, ``$comment``) are ignored. Any
other keyword makes :func:`check_schema` fail, so a schema never silently
validates less than it appears to.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

SUPPORTED = frozenset(
    {
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "anyOf",
    }
)
ANNOTATIONS = frozenset(
    {"title", "description", "default", "examples", "$schema", "$id", "$comment"}
)
TYPES = frozenset({"string", "number", "integer", "boolean", "object", "array", "null"})


class SchemaError(ValueError):
    """The schema uses an unsupported keyword or is malformed."""


def check_schema(schema: Any, path: str = "schema") -> None:
    """Raise :class:`SchemaError` unless ``schema`` only uses supported keywords."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaError(f"{path} must be an object or boolean")
    node = cast("dict[str, Any]", schema)
    for keyword in node:
        if keyword not in SUPPORTED and keyword not in ANNOTATIONS:
            raise SchemaError(f"{path}: unsupported keyword {keyword!r}")
    for t in _as_list(node.get("type")):
        if t is not None and t not in TYPES:
            raise SchemaError(f"{path}: unknown type {t!r}")
    if "pattern" in node:
        try:
            re.compile(node["pattern"])
        except (re.error, TypeError) as exc:
            raise SchemaError(f"{path}: invalid pattern: {exc}") from exc
    properties: Any = node.get("properties", {})
    if not isinstance(properties, dict):
        raise SchemaError(f"{path}.properties must be an object")
    for key, sub in cast("dict[str, Any]", properties).items():
        check_schema(sub, f"{path}.properties.{key}")
    if "items" in node:
        check_schema(node["items"], f"{path}.items")
    if "additionalProperties" in node:
        check_schema(node["additionalProperties"], f"{path}.additionalProperties")
    if "anyOf" in node:
        options: Any = node["anyOf"]
        if not isinstance(options, list) or not options:
            raise SchemaError(f"{path}.anyOf must be a non-empty list")
        for i, sub in enumerate(cast("list[Any]", options)):
            check_schema(sub, f"{path}.anyOf[{i}]")


def validate(instance: Any, schema: Any, path: str = "$") -> list[str]:
    """Return a list of error messages; empty means ``instance`` is valid."""
    if schema is True:
        return []
    if schema is False:
        return [f"{path}: no value is allowed here"]
    node = cast("Mapping[str, Any]", schema)
    errors: list[str] = []

    if "type" in node:
        types = cast("list[str]", _as_list(node["type"]))
        if not any(_is_type(instance, t) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {_type_name(instance)}"]
    if "enum" in node and not any(_equal(instance, option) for option in node["enum"]):
        errors.append(f"{path}: {instance!r} is not one of {list(node['enum'])!r}")
    if "const" in node and not _equal(instance, node["const"]):
        errors.append(f"{path}: expected {node['const']!r}, got {instance!r}")
    if "anyOf" in node and not any(not validate(instance, sub, path) for sub in node["anyOf"]):
        errors.append(f"{path}: does not match any of the allowed schemas")

    if isinstance(instance, str):
        errors += _check_string(instance, node, path)
    elif _is_type(instance, "number"):
        errors += _check_number(instance, node, path)
    elif isinstance(instance, list):
        errors += _check_array(cast("list[Any]", instance), node, path)
    elif isinstance(instance, dict):
        errors += _check_object(cast("dict[str, Any]", instance), node, path)
    return errors


def _check_string(value: str, node: Mapping[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if "minLength" in node and len(value) < node["minLength"]:
        errors.append(f"{path}: shorter than minLength {node['minLength']}")
    if "maxLength" in node and len(value) > node["maxLength"]:
        errors.append(f"{path}: longer than maxLength {node['maxLength']}")
    if "pattern" in node and re.search(node["pattern"], value) is None:
        errors.append(f"{path}: does not match pattern {node['pattern']!r}")
    return errors


def _check_number(value: float, node: Mapping[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if "minimum" in node and value < node["minimum"]:
        errors.append(f"{path}: {value} is less than minimum {node['minimum']}")
    if "maximum" in node and value > node["maximum"]:
        errors.append(f"{path}: {value} is greater than maximum {node['maximum']}")
    return errors


def _check_array(value: list[Any], node: Mapping[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if "minItems" in node and len(value) < node["minItems"]:
        errors.append(f"{path}: fewer than minItems {node['minItems']}")
    if "maxItems" in node and len(value) > node["maxItems"]:
        errors.append(f"{path}: more than maxItems {node['maxItems']}")
    if "items" in node:
        for i, item in enumerate(value):
            errors += validate(item, node["items"], f"{path}[{i}]")
    return errors


def _check_object(value: dict[str, Any], node: Mapping[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    for key in node.get("required", []):
        if key not in value:
            errors.append(f"{path}: missing required property {key!r}")
    properties: Mapping[str, Any] = node.get("properties", {})
    for key, sub in properties.items():
        if key in value:
            errors += validate(value[key], sub, f"{path}.{key}")
    if "additionalProperties" in node:
        for key, item in value.items():
            if key not in properties:
                errors += validate(item, node["additionalProperties"], f"{path}.{key}")
    return errors


def _as_list(value: Any) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else [value]


def _is_type(value: Any, name: str) -> bool:
    if name == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if name == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, int | float)
    return {
        "string": isinstance(value, str),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "null": value is None,
    }.get(name, False)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    names: dict[str, str] = {"str": "string", "list": "array", "dict": "object"}
    kind = type(value).__name__
    return names.get(kind, kind)


def _equal(a: Any, b: Any) -> bool:
    """JSON equality: ``True`` is not ``1``."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b
