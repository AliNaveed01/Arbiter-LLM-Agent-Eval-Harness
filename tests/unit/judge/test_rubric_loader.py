from pathlib import Path

import pytest

from agentgauge.judge import RubricLoadError, load_rubric

GOOD = """name: helpfulness
criteria:
  - answers the question
scale: 5
pass_at: 4
"""


def _write(tmp_path: Path, text: str, name: str = "rubric.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_a_rubric(tmp_path: Path) -> None:
    rubric = load_rubric(_write(tmp_path, GOOD))
    assert rubric.name == "helpfulness"
    assert (rubric.scale.levels, rubric.threshold) == (5, 4)


def test_validation_errors_point_at_the_line(tmp_path: Path) -> None:
    path = _write(tmp_path, GOOD.replace("pass_at: 4", "pass_at: 9"))
    with pytest.raises(RubricLoadError, match=r"rubric\.yaml:5: pass_at") as info:
        load_rubric(path)
    assert info.value.line == 5


def test_nested_error_lines(tmp_path: Path) -> None:
    path = _write(tmp_path, GOOD.replace("scale: 5", "scale: 1"))
    with pytest.raises(RubricLoadError) as info:
        load_rubric(path)
    assert info.value.line == 4


def test_invalid_yaml_reports_the_line(tmp_path: Path) -> None:
    with pytest.raises(RubricLoadError, match="invalid YAML") as info:
        load_rubric(_write(tmp_path, "name: r\ncriteria: [a\n"))
    assert info.value.line == 2


def test_top_level_must_be_a_mapping(tmp_path: Path) -> None:
    for text in ("", "- a\n- b\n"):
        with pytest.raises(RubricLoadError, match="top level must be a mapping"):
            load_rubric(_write(tmp_path, text))


def test_unsupported_and_missing_files(tmp_path: Path) -> None:
    with pytest.raises(RubricLoadError, match="unsupported file type"):
        load_rubric(_write(tmp_path, GOOD, "rubric.json"))
    with pytest.raises(RubricLoadError, match="cannot read file"):
        load_rubric(tmp_path / "missing.yaml")
