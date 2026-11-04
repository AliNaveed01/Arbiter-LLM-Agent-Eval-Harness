import pytest
from pydantic import BaseModel, ValidationError

from agentgauge.core.yamlio import YamlProblem, describe, line_at, parse_yaml


def test_parse_returns_node_tree_and_data() -> None:
    root, data = parse_yaml("a: 1\nb: [x, y]\n")
    assert root is not None
    assert data == {"a": 1, "b": ["x", "y"]}


def test_parse_error_carries_a_line() -> None:
    with pytest.raises(YamlProblem) as info:
        parse_yaml("a: 1\nb: [x, y\n")
    assert info.value.line == 2
    assert info.value.message.startswith("invalid YAML")


def test_line_at_finds_nested_nodes_and_falls_back_to_parent() -> None:
    root, _ = parse_yaml("top:\n  items:\n    - one\n    - two\n")
    assert root is not None
    assert line_at(root, ("top", "items", 1)) == 4
    assert line_at(root, ("top", "missing")) == 2
    assert line_at(root, ("top", "items", 9)) == 3


def test_describe_names_the_field() -> None:
    class M(BaseModel):
        n: int

    with pytest.raises(ValidationError) as info:
        M.model_validate({"n": "x"})
    assert describe(info.value).startswith("n: ")
