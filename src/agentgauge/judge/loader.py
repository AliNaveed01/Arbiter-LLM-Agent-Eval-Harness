"""Load a rubric from a YAML file with file/line error reporting."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from agentgauge.core.yamlio import FileLoadError, YamlProblem, describe, line_at, parse_yaml
from agentgauge.judge.rubric import Rubric


class RubricLoadError(FileLoadError):
    """Raised when a rubric file cannot be read or is invalid."""


def load_rubric(path: str | Path) -> Rubric:
    """Load a rubric from a ``.yaml`` or ``.yml`` file."""
    p = Path(path)
    if p.suffix.lower() not in {".yaml", ".yml"}:
        raise RubricLoadError(p, f"unsupported file type {p.suffix!r}; use .yaml or .yml")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RubricLoadError(p, f"cannot read file: {exc.strerror or exc}") from exc
    try:
        root, data = parse_yaml(text)
    except YamlProblem as exc:
        raise RubricLoadError(p, exc.message, exc.line) from exc
    if root is None or not isinstance(data, dict):
        raise RubricLoadError(p, "top level must be a mapping with 'name', 'criteria', 'scale'", 1)
    try:
        return Rubric.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise RubricLoadError(p, describe(exc), line_at(root, first["loc"])) from exc
