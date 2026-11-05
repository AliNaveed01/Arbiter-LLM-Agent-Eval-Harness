from pathlib import Path

import pytest

from agentgauge.core import ScorerSpec, SuiteLoadError, load_suite

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "suites"


def test_load_yaml() -> None:
    suite = load_suite(FIXTURES / "valid.yaml")
    assert suite.name == "basic"
    assert suite.scorers == (ScorerSpec(name="exact_match"),)
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


def test_yaml_multi_turn_tool_conversation() -> None:
    case = load_suite(FIXTURES / "tool_conversation.yaml").cases[0]
    assert [m.role for m in case.input] == ["system", "user", "assistant", "tool", "user"]
    assert case.input[2].tool_calls[0].name == "get_weather"
    assert case.input[3].tool_call_id == case.input[2].tool_calls[0].id


def test_tool_message_without_id_reports_line() -> None:
    path = FIXTURES / "invalid_tool_message.yaml"
    with pytest.raises(SuiteLoadError) as info:
        load_suite(path)
    assert info.value.line == 5
    assert "tool_call_id" in info.value.message


def test_yaml_scorers_may_have_params() -> None:
    suite = load_suite(FIXTURES / "scorer_params.yaml")
    assert suite.scorers == (
        ScorerSpec(name="exact_match"),
        ScorerSpec(name="numeric_tolerance", params={"abs_tol": 0.01}),
    )


def test_yaml_provider_block() -> None:
    suite = load_suite(FIXTURES / "with_provider.yaml")
    assert suite.provider is not None
    assert (suite.provider.type, suite.provider.model) == ("fake", "scripted")
    assert suite.provider.responses == {"2+2?": "4"}


def test_provider_is_optional() -> None:
    assert load_suite(FIXTURES / "valid.yaml").provider is None


def test_suite_tools_load_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        "name: s\n"
        "tools:\n"
        "  - name: get_weather\n"
        "    description: Current weather for a city\n"
        "    parameters: {type: object, properties: {city: {type: string}}}\n"
        "cases:\n"
        "  - {id: a, input: hi}\n"
    )
    (tool,) = load_suite(path).tools
    assert (tool.name, tool.parameters["properties"]["city"]) == ("get_weather", {"type": "string"})


def test_agent_block_and_tool_mocks_load_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        "name: s\n"
        "agent: {max_steps: 4}\n"
        "tool_mocks:\n"
        "  - {tool: get_weather, arguments: {city: Paris}, result: sunny}\n"
        "  - {tool: get_weather, result: unknown city}\n"
        "cases:\n"
        "  - {id: a, input: hi}\n"
    )
    suite = load_suite(path)
    assert suite.agent is not None and suite.agent.max_steps == 4
    assert [(m.tool, m.arguments, m.result) for m in suite.tool_mocks] == [
        ("get_weather", {"city": "Paris"}, "sunny"),
        ("get_weather", None, "unknown city"),
    ]


def test_invalid_agent_block_reports_its_line(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text("name: s\nagent:\n  max_steps: 0\ncases: []\n")
    with pytest.raises(SuiteLoadError) as info:
        load_suite(path)
    assert info.value.line == 3


def test_relative_rubric_paths_resolve_against_the_suite_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "suites"
    folder.mkdir()
    (folder / "rubric.yaml").write_text("name: r\ncriteria: [c]\nscale: binary\n")
    (folder / "suite.yaml").write_text(
        "name: s\n"
        "scorers:\n"
        "  - name: llm_judge\n"
        "    params: {rubric: rubric.yaml, judge: {type: fake}}\n"
        "  - name: exact_match\n"
        "cases: [{id: a, input: hi}]\n"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    suite = load_suite(folder / "suite.yaml")
    assert suite.scorers[0].params["rubric"] == str(folder / "rubric.yaml")
    assert suite.scorers[0].params["judge"] == {"type": "fake"}
    assert suite.scorers[1].params == {}


@pytest.mark.parametrize("rubric", ["missing.yaml", "{name: r}"])
def test_rubric_paths_that_do_not_exist_next_to_the_suite_are_left_alone(
    tmp_path: Path, rubric: str
) -> None:
    (tmp_path / "suite.yaml").write_text(
        f"name: s\nscorers:\n  - name: llm_judge\n    params: {{rubric: {rubric}}}\ncases: []\n"
    )
    (spec,) = load_suite(tmp_path / "suite.yaml").scorers
    assert spec.params["rubric"] in ("missing.yaml", {"name": "r"})


def test_absolute_rubric_paths_are_untouched(tmp_path: Path) -> None:
    rubric = tmp_path / "rubric.yaml"
    rubric.write_text("name: r\ncriteria: [c]\nscale: binary\n")
    (tmp_path / "suite.yaml").write_text(
        f"name: s\nscorers:\n  - name: llm_judge\n    params: {{rubric: {rubric}}}\ncases: []\n"
    )
    assert load_suite(tmp_path / "suite.yaml").scorers[0].params["rubric"] == str(rubric)
