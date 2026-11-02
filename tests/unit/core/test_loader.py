from pathlib import Path

import pytest

from agentgauge.core import SuiteLoadError, load_suite

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "suites"


def test_load_yaml() -> None:
    suite = load_suite(FIXTURES / "valid.yaml")
    assert suite.name == "basic"
    assert suite.scorers == ("exact_match",)
    assert [c.id for c in suite.cases] == ["add", "capital"]
    assert suite.cases[1].metadata == {"tag": "geo"}


def test_load_jsonl_skips_blank_lines_and_names_suite_after_file() -> None:
    suite = load_suite(FIXTURES / "valid.jsonl")
    assert suite.name == "valid"
    assert [c.id for c in suite.cases] == ["add", "capital"]


def test_accepts_str_path() -> None:
    assert load_suite(str(FIXTURES / "valid.yaml")).name == "basic"


@pytest.mark.parametrize(
    ("name", "line", "fragment"),
    [
        ("invalid_syntax.yaml", 4, "invalid YAML"),
        ("invalid_field.yaml", 5, "cases.1.input"),
        ("invalid_type.yaml", 4, "cases.0.input"),
        ("not_a_mapping.yaml", 1, "top level must be a mapping"),
        ("invalid_json.jsonl", 2, "invalid JSON"),
        ("invalid_case.jsonl", 2, "input"),
    ],
)
def test_invalid_input_reports_file_and_line(name: str, line: int, fragment: str) -> None:
    path = FIXTURES / name
    with pytest.raises(SuiteLoadError) as info:
        load_suite(path)
    err = info.value
    assert err.path == path
    assert err.line == line
    assert fragment in err.message
    assert str(err).startswith(f"{path}:{line}: ")


def test_missing_top_level_field_points_at_top() -> None:
    path = FIXTURES / "invalid_toplevel.yaml"
    with pytest.raises(SuiteLoadError) as info:
        load_suite(path)
    assert info.value.line == 1
    assert "name" in info.value.message


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SuiteLoadError, match="cannot read file"):
        load_suite(tmp_path / "nope.yaml")


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "suite.txt"
    path.write_text("x")
    with pytest.raises(SuiteLoadError, match="unsupported file type"):
        load_suite(path)


def test_empty_yaml(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("")
    with pytest.raises(SuiteLoadError, match="top level"):
        load_suite(path)


def test_yaml_input_may_be_string_or_message_list() -> None:
    suite = load_suite(FIXTURES / "messages.yaml")
    assert [m.role for m in suite.cases[0].input] == ["user"]
    assert [m.role for m in suite.cases[1].input] == ["system", "user"]
