"""Load suites from YAML or JSONL files with file/line error reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from agentgauge.core.models import Suite, TestCase


class SuiteLoadError(Exception):
    """Raised when a suite file cannot be read or is invalid."""

    def __init__(self, path: Path, message: str, line: int | None = None) -> None:
        self.path = path
        self.line = line
        self.message = message
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{location}: {message}")


def load_suite(path: str | Path) -> Suite:
    """Load a suite from a ``.yaml``/``.yml`` or ``.jsonl`` file."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in {".yaml", ".yml", ".jsonl"}:
        raise SuiteLoadError(p, f"unsupported file type {suffix!r}; use .yaml, .yml or .jsonl")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise SuiteLoadError(p, f"cannot read file: {exc.strerror or exc}") from exc
    if suffix == ".jsonl":
        return _load_jsonl(p, text)
    return _load_yaml(p, text)


def _load_jsonl(path: Path, text: str) -> Suite:
    cases: list[TestCase] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SuiteLoadError(path, f"invalid JSON: {exc.msg}", lineno) from exc
        try:
            cases.append(TestCase.model_validate(data))
        except ValidationError as exc:
            raise SuiteLoadError(path, _describe(exc), lineno) from exc
    return Suite(name=path.stem, cases=tuple(cases))


def _load_yaml(path: Path, text: str) -> Suite:
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
        raise SuiteLoadError(path, f"invalid YAML: {problem}", line) from exc
    if root is None or not isinstance(data, dict):
        raise SuiteLoadError(path, "top level must be a mapping with 'name' and 'cases'", 1)
    try:
        return Suite.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        line = _line_at(root, first["loc"])
        raise SuiteLoadError(path, _describe(exc), line) from exc


def _line_at(root: yaml.Node, loc: tuple[int | str, ...]) -> int:
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


def _describe(exc: ValidationError) -> str:
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"])
    where = f"{field}: " if field else ""
    return f"{where}{first['msg']}"
