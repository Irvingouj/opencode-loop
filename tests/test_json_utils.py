from opencode_loop.json_utils import (
    find_first_json_object,
    parse_json_payload,
    _matches_type,
    parse_json_with_repair,
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


def test_parse_json_with_repair_uses_semantic_validator(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_run_opencode(message, args, session_id, use_continue, stream_label):
        calls.append((message, use_continue))
        return ('{"is_done": false, "reason": "keep going", "next_task_prompt": "do x"}', "ses_2")

    monkeypatch.setattr("opencode_loop.runner.run_opencode", fake_run_opencode)

    data, session, repaired = parse_json_with_repair(
        '{"is_done": false, "reason": "keep going"}',
        args=object(),
        session_id="ses_1",
        phase="evaluator",
        schema={
            "required": {"is_done": "bool", "reason": "str"},
            "optional": {"next_task_prompt": "str"},
        },
        attempts=1,
        use_continue_on_repair=True,
        semantic_validator=lambda payload: (
            ["missing next_task_prompt"]
            if payload.get("is_done") is False
            and not str(payload.get("next_task_prompt", "")).strip()
            else []
        ),
    )

    assert data["next_task_prompt"] == "do x"
    assert session == "ses_2"
    assert repaired is True
    assert calls
    assert "Hi, you returned a evaluator response" in calls[0][0]
    assert calls[0][1] is True
