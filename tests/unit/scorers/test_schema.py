import re
from typing import Any

import pytest

from agentgauge.scorers.schema import SchemaError, check_schema, validate


@pytest.mark.parametrize(
    ("instance", "type_name"),
    [
        ("x", "string"),
        (1, "integer"),
        (1.0, "integer"),
        (1, "number"),
        (1.5, "number"),
        (True, "boolean"),
        (None, "null"),
        ({}, "object"),
        ([], "array"),
    ],
)
def test_type_accepts_matching_values(instance: Any, type_name: str) -> None:
    assert validate(instance, {"type": type_name}) == []


@pytest.mark.parametrize(
    ("instance", "type_name", "got"),
    [
        (1, "string", "integer"),
        (1.5, "integer", "number"),
        (True, "integer", "boolean"),
        (True, "number", "boolean"),
        ("1", "number", "string"),
        (0, "boolean", "integer"),
        ([], "object", "array"),
        ({}, "array", "object"),
        (None, "string", "null"),
        ("x", "null", "string"),
    ],
)
def test_type_rejects_mismatches(instance: Any, type_name: str, got: str) -> None:
    assert validate(instance, {"type": type_name}) == [f"$: expected {type_name}, got {got}"]


def test_type_list_accepts_any_listed_type() -> None:
    schema = {"type": ["string", "null"]}
    assert validate(None, schema) == []
    assert validate("x", schema) == []
    assert validate(1, schema) == ["$: expected string or null, got integer"]


def test_unknown_python_type_is_named() -> None:
    assert validate(object(), {"type": "string"}) == ["$: expected string, got object"]


def test_enum_and_const() -> None:
    assert validate("a", {"enum": ["a", "b"]}) == []
    assert validate("c", {"enum": ["a", "b"]}) == ["$: 'c' is not one of ['a', 'b']"]
    assert validate(1, {"const": 1}) == []
    assert validate(2, {"const": 1}) == ["$: expected 1, got 2"]


def test_json_equality_distinguishes_bool_from_int() -> None:
    assert validate(True, {"enum": [1]}) != []
    assert validate(1, {"const": True}) != []
    assert validate(True, {"const": True}) == []


def test_string_constraints() -> None:
    schema = {"type": "string", "minLength": 2, "maxLength": 4, "pattern": "^a"}
    assert validate("abc", schema) == []
    assert validate("a", schema) == ["$: shorter than minLength 2"]
    assert validate("abcde", schema) == ["$: longer than maxLength 4"]
    assert validate("bcd", schema) == ["$: does not match pattern '^a'"]


def test_number_constraints() -> None:
    schema = {"type": "number", "minimum": 0, "maximum": 10}
    assert validate(5, schema) == []
    assert validate(0, schema) == [] and validate(10, schema) == []
    assert validate(-1, schema) == ["$: -1 is less than minimum 0"]
    assert validate(11, schema) == ["$: 11 is greater than maximum 10"]


def test_bool_is_not_checked_against_numeric_bounds() -> None:
    assert validate(True, {"minimum": 5}) == []


def test_array_constraints_and_items() -> None:
    schema = {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "integer"}}
    assert validate([1, 2], schema) == []
    assert validate([], schema) == ["$: fewer than minItems 1"]
    assert validate([1, 2, 3], schema) == ["$: more than maxItems 2"]
    assert validate([1, "x"], schema) == ["$[1]: expected integer, got string"]


def test_object_properties_required_and_nesting() -> None:
    schema = {
        "type": "object",
        "required": ["name", "tags"],
        "properties": {
            "name": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
    assert validate({"name": "a", "tags": ["x"]}, schema) == []
    assert validate({"tags": ["x"]}, schema) == ["$: missing required property 'name'"]
    errors = validate({"name": "a", "tags": [1]}, schema)
    assert errors == ["$.tags[0]: expected string, got integer"]


def test_all_errors_are_collected() -> None:
    schema = {"type": "object", "required": ["a", "b"]}
    assert len(validate({}, schema)) == 2


def test_additional_properties() -> None:
    props = {"properties": {"a": {}}}
    assert validate({"a": 1, "b": 2}, props) == []
    assert validate({"a": 1, "b": 2}, {**props, "additionalProperties": False}) == [
        "$.b: no value is allowed here"
    ]
    typed = {**props, "additionalProperties": {"type": "string"}}
    assert validate({"a": 1, "b": "x"}, typed) == []
    assert validate({"a": 1, "b": 2}, typed) == ["$.b: expected string, got integer"]
    assert validate({"a": 1}, {**props, "additionalProperties": True}) == []


def test_any_of() -> None:
    schema = {"anyOf": [{"type": "string"}, {"type": "integer", "minimum": 0}]}
    assert validate("x", schema) == []
    assert validate(3, schema) == []
    assert validate(-3, schema) == ["$: does not match any of the allowed schemas"]


def test_boolean_schemas() -> None:
    assert validate(1, True) == []
    assert validate(1, False) == ["$: no value is allowed here"]


def test_annotations_are_ignored() -> None:
    schema = {"title": "t", "description": "d", "default": 1, "$schema": "x", "type": "integer"}
    check_schema(schema)
    assert validate(1, schema) == []


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"$ref": "#/x"}, "unsupported keyword '$ref'"),
        ({"allOf": []}, "unsupported keyword 'allOf'"),
        ({"properties": {"a": {"format": "email"}}}, "schema.properties.a: unsupported keyword"),
        ({"items": {"oneOf": []}}, "schema.items: unsupported keyword 'oneOf'"),
        ({"anyOf": [{"not": {}}]}, "schema.anyOf[0]: unsupported keyword 'not'"),
        ({"additionalProperties": {"uniqueItems": True}}, "additionalProperties: unsupported"),
        ({"type": "strin"}, "unknown type 'strin'"),
        ({"type": ["string", "nope"]}, "unknown type 'nope'"),
        ({"pattern": "("}, "invalid pattern"),
        ({"pattern": 5}, "invalid pattern"),
        ({"properties": []}, "schema.properties must be an object"),
        ({"anyOf": []}, "anyOf must be a non-empty list"),
        ({"anyOf": "x"}, "anyOf must be a non-empty list"),
        ([], "schema must be an object or boolean"),
        ({"items": 3}, "schema.items must be an object or boolean"),
    ],
)
def test_check_schema_rejects_unsupported_or_malformed(schema: Any, message: str) -> None:
    with pytest.raises(SchemaError, match=re.escape(message)):
        check_schema(schema)


def test_check_schema_accepts_boolean_subschemas() -> None:
    check_schema({"items": True, "additionalProperties": False})
