from agentgauge.scorers.arguments import normalise, parse_arguments, same_arguments


def test_normalise_folds_strings_recursively_and_leaves_other_values() -> None:
    assert normalise({"a": [" X ", 1, {"b": "Y"}], "n": 2.5, "t": True}) == {
        "a": ["x", 1, {"b": "y"}],
        "n": 2.5,
        "t": True,
    }


def test_same_arguments() -> None:
    assert same_arguments({"city": " Paris"}, {"city": "paris"})
    assert same_arguments({"n": 1}, {"n": 1.0})
    assert not same_arguments({"n": 1}, {"n": 2})
    assert not same_arguments({"a": 1}, {"a": 1, "b": 2})


def test_parse_arguments_accepts_only_json_objects() -> None:
    assert parse_arguments('{"a": 1}') == {"a": 1}
    assert parse_arguments("{}") == {}
    for bad in ("not json", "[1]", '"s"', "3", "{a: 1"):
        assert parse_arguments(bad) is None
