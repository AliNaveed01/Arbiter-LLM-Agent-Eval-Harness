"""Human labels: the ground truth a judge is calibrated against.

A label file is YAML (a list of labels, or a mapping with a ``labels`` list) or
JSONL (one label object per line)::

    - case_id: capital-france
      label: 1
      annotator: ana     # optional

``label`` is an integer on the rubric's scale. For convenience ``true``/``false``
and ``pass``/``fail`` mean 1 and 0, so binary labels read naturally.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError, field_validator

from agentgauge.core.yamlio import FileLoadError, YamlProblem, describe, line_at, parse_yaml


class Label(BaseModel):
    """A human's verdict on one case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    label: StrictInt
    annotator: str | None = None

    @field_validator("label", mode="before")
    @classmethod
    def _friendly_binary(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, str) and value.strip().lower() in {"pass", "fail"}:
            return 1 if value.strip().lower() == "pass" else 0
        return value


Loc = tuple[int | str, ...]
Entry = tuple[Callable[[Loc], int], Any]


class LabelLoadError(FileLoadError):
    """Raised when a label file cannot be read or is invalid."""


def load_labels(path: str | Path) -> tuple[Label, ...]:
    """Load labels from a ``.yaml``/``.yml`` or ``.jsonl`` file.

    A case id may appear only once: calibration compares one human verdict to
    one judge verdict per case.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in {".yaml", ".yml", ".jsonl"}:
        raise LabelLoadError(p, f"unsupported file type {suffix!r}; use .yaml, .yml or .jsonl")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise LabelLoadError(p, f"cannot read file: {exc.strerror or exc}") from exc
    entries = _jsonl_entries(p, text) if suffix == ".jsonl" else _yaml_entries(p, text)
    labels: list[Label] = []
    first_line: dict[str, int] = {}
    for line, data in entries:
        try:
            label = Label.model_validate(data)
        except ValidationError as exc:
            raise LabelLoadError(p, describe(exc), line(exc.errors()[0]["loc"])) from exc
        if label.case_id in first_line:
            raise LabelLoadError(
                p,
                f"case_id {label.case_id!r} is labelled twice "
                f"(first at line {first_line[label.case_id]})",
                line(("case_id",)),
            )
        first_line[label.case_id] = line(("case_id",))
        labels.append(label)
    if not labels:
        raise LabelLoadError(p, "no labels found")
    return tuple(labels)


def _jsonl_entries(path: Path, text: str) -> list[Entry]:
    entries: list[Entry] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LabelLoadError(path, f"invalid JSON: {exc.msg}", lineno) from exc
        entries.append((lambda _loc, n=lineno: n, data))
    return entries


def _yaml_entries(path: Path, text: str) -> list[Entry]:
    try:
        root, data = parse_yaml(text)
    except YamlProblem as exc:
        raise LabelLoadError(path, exc.message, exc.line) from exc
    prefix: Loc = ()
    if isinstance(data, dict):
        data = data.get("labels")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        prefix = ("labels",)
    if root is None or not isinstance(data, list):
        raise LabelLoadError(
            path, "top level must be a list of labels or a mapping with a 'labels' list", 1
        )
    items: list[Any] = data  # pyright: ignore[reportUnknownVariableType]
    tree = root

    def locator(index: int) -> Callable[[Loc], int]:
        return lambda loc: line_at(tree, (*prefix, index, *loc))

    return [(locator(i), item) for i, item in enumerate(items)]
