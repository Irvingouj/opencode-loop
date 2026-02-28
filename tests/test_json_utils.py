from opencode_loop.json_utils import (
    find_first_json_object,
    parse_json_payload,
    _matches_type,
    validate_against_schema,
)
import pytest


def test_find_first_json_object_basic():
    assert find_first_json_object('prefix {"key": "val"} suffix') == '{"key": "val"}'


def test_find_first_json_object_none():
    with pytest.raises(ValueError):
        find_first_json_object("no json here")


def test_parse_json_payload_plain():
    assert parse_json_payload('{"a": 1}') == {"a": 1}


def test_parse_json_payload_fenced():
    assert parse_json_payload('```json\n{"a": 1}\n```') == {"a": 1}


def test_matches_type_str():
    assert _matches_type("hello", "str")
    assert not _matches_type(1, "str")


def test_matches_type_list_str():
    assert _matches_type(["a", "b"], "list[str]")
    assert not _matches_type(["a", 1], "list[str]")


def test_validate_schema_passes():
    schema = {"required": {"name": "str"}, "optional": {"count": "int"}}
    validate_against_schema({"name": "foo"}, schema, "test")


def test_validate_schema_missing_required():
    schema = {"required": {"name": "str"}}
    with pytest.raises(ValueError, match="missing required field"):
        validate_against_schema({}, schema, "test")
