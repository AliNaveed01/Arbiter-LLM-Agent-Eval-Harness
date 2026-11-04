"""YAML parsing that keeps line numbers, shared by the suite, rubric and label loaders."""

from __future__ import annotations

from typing import Any, cast

import yaml
from pydantic import ValidationError


class YamlProblem(Exception):
    """The text is not valid YAML; ``line`` is 1-based when known."""

    def __init__(self, message: str, line: int | None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


def parse_yaml(text: str) -> tuple[yaml.Node | None, Any]:
    """Parse ``text`` into its node tree (for line lookups) and its plain data."""
    try:
        # types-PyYAML leaves compose()'s return type unannotated.
        root = cast(
            "yaml.Node | None",
            yaml.compose(text, Loader=yaml.SafeLoader),  # pyright: ignore[reportUnknownMemberType]
        )
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        problem = getattr(exc, "problem", None) or "invalid YAML"
        mark = getattr(exc, "problem_mark", None)
        context = getattr(exc, "context_mark", None)
        if context is not None and "<stream end>" in problem:
            mark = context  # unclosed construct: point at where it opened
        line = mark.line + 1 if mark is not None else None
        raise YamlProblem(f"invalid YAML: {problem}", line) from exc
    return root, data


def line_at(root: yaml.Node, loc: tuple[int | str, ...]) -> int:
    """Line of the deepest YAML node on ``loc``, falling back to the nearest parent."""
    node = root
    for part in loc:
        child: yaml.Node | None = None
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if isinstance(key, yaml.ScalarNode) and key.value == part:
                    child = value
                    break
        elif (
            isinstance(node, yaml.SequenceNode)
            and isinstance(part, int)
            and 0 <= part < len(node.value)
        ):
            child = node.value[part]
        if child is None:
            break
        node = child
    return node.start_mark.line + 1


def describe(exc: ValidationError) -> str:
    """The first validation error as ``field: message``."""
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"])
    where = f"{field}: " if field else ""
    return f"{where}{first['msg']}"
