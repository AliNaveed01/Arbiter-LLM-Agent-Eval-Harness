"""Load suites from YAML or JSONL files with file/line error reporting."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from agentgauge.core.models import ScorerSpec, Suite, TestCase
from agentgauge.core.yamlio import FileLoadError, YamlProblem, describe, line_at, parse_yaml


class SuiteLoadError(FileLoadError):
    """Raised when a suite file cannot be read or is invalid."""


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
    return _resolve_rubric_paths(_load_yaml(p, text), p.parent)


def _resolve_rubric_paths(suite: Suite, base: Path) -> Suite:
    """Make a relative ``rubric`` file path in an ``llm_judge`` scorer relative to the suite.

    A path is rewritten only when the file exists next to the suite, so a path that was
    meant to be relative to the working directory keeps working.
    """
    specs: list[ScorerSpec] = []
    for spec in suite.scorers:
        rubric = spec.params.get("rubric")
        if spec.name == "llm_judge" and isinstance(rubric, str):
            candidate = base / rubric
            if not Path(rubric).is_absolute() and candidate.is_file():
                spec = spec.model_copy(update={"params": {**spec.params, "rubric": str(candidate)}})
        specs.append(spec)
    return suite.model_copy(update={"scorers": tuple(specs)})


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
            raise SuiteLoadError(path, describe(exc), lineno) from exc
    return Suite(name=path.stem, cases=tuple(cases))


def _load_yaml(path: Path, text: str) -> Suite:
    try:
        root, data = parse_yaml(text)
    except YamlProblem as exc:
        raise SuiteLoadError(path, exc.message, exc.line) from exc
    if root is None or not isinstance(data, dict):
        raise SuiteLoadError(path, "top level must be a mapping with 'name' and 'cases'", 1)
    try:
        return Suite.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise SuiteLoadError(path, describe(exc), line_at(root, first["loc"])) from exc
