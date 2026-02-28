from __future__ import annotations

import json
from typing import Any, Callable

from opencode_loop.templates import schema_text


def find_first_json_object(s: str) -> str:
    start = s.find("{")
    if start < 0:
        raise ValueError("No JSON object found")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("Unbalanced JSON object")


def parse_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = json.loads(find_first_json_object(cleaned))

    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "str":
        return isinstance(value, str)
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "float":
        return isinstance(value, float)
    if expected == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(
            value, float
        )
    if expected in ("object", "dict"):
        return isinstance(value, dict)
    if expected in ("array", "list"):
        return isinstance(value, list)
    if expected == "list[str]":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if expected == "list[object]":
        return isinstance(value, list) and all(isinstance(x, dict) for x in value)
    if expected == "list[number]":
        return isinstance(value, list) and all(
            _matches_type(x, "number") for x in value
        )
    return False


def validate_against_schema(
    data: dict[str, Any], schema: dict[str, Any], phase: str
) -> None:
    required = schema.get("required", {})
    optional = schema.get("optional", {})
    if required and not isinstance(required, dict):
        raise ValueError(f"{phase} schema 'required' must be an object")
    if optional and not isinstance(optional, dict):
        raise ValueError(f"{phase} schema 'optional' must be an object")

    for key, typ in required.items():
        if key not in data:
            raise ValueError(f"{phase} JSON missing required field: {key}")
        if not _matches_type(data[key], str(typ)):
            raise ValueError(
                f"{phase} JSON field '{key}' has wrong type (expected {typ})"
            )

    for key, typ in optional.items():
        if key in data and not _matches_type(data[key], str(typ)):
            raise ValueError(
                f"{phase} JSON field '{key}' has wrong type (expected {typ})"
            )


def normalize_wrapped_schema_output(
    data: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(data, dict):
        return data
    req = data.get("required")
    opt = data.get("optional")
    if not isinstance(req, dict):
        return data

    required_fields = schema.get("required", {})
    if not isinstance(required_fields, dict) or not required_fields:
        return data

    merged: dict[str, Any] = {}
    merged.update(req)
    if isinstance(opt, dict):
        merged.update(opt)
    return merged


def _format_repair_issues(issues: list[str]) -> str:
    if not issues:
        return "machine parsing/validation failed"
    return "; ".join(issues)


def parse_json_with_repair(
    text: str,
    args,
    session_id: str,
    phase: str,
    schema: dict[str, Any],
    attempts: int,
    use_continue_on_repair: bool,
    semantic_validator: Callable[[dict[str, Any]], list[str]] | None = None,
) -> tuple[dict[str, Any], str, bool]:
    from opencode_loop.runner import run_opencode

    last_issues: list[str] = []
    try:
        data = parse_json_payload(text)
        data = normalize_wrapped_schema_output(data, schema)
        validate_against_schema(data, schema, phase)
        if semantic_validator is not None:
            issues = semantic_validator(data)
            if issues:
                last_issues = issues
                raise ValueError(f"{phase} JSON semantic validation failed: {issues}")
        return data, session_id, False
    except Exception as exc:
        last_exc: Exception = exc

    current_text = text
    current_session = session_id
    for n in range(attempts):
        snippet = current_text[-1800:] if current_text else "(empty)"
        from opencode_loop.tui import console

        console.log(
            f"[yellow]⚠ {phase} output invalid — attempting repair (attempt {n + 1}/{attempts})[/yellow]"
        )
        issues_text = _format_repair_issues(last_issues)
        repair_prompt = (
            f"Hi, you returned a {phase} response that was invalid because {issues_text}.\n"
            "Return ONE valid JSON object only, no markdown, no code fences, no commentary.\n"
            "Keep same semantics as your previous answer.\n"
            "IMPORTANT: Do NOT wrap fields under keys like 'required' or 'optional'.\n"
            "Return the ACTUAL payload object directly (top-level fields only).\n"
            "The output MUST satisfy this schema:\n"
            f"{schema_text(schema)}\n\n"
            f"Previous response (tail):\n{snippet}"
        )
        repaired_text, current_session = run_opencode(
            repair_prompt,
            args,
            current_session,
            use_continue=use_continue_on_repair,
            stream_label=f"{phase}:repair",
        )
        current_text = repaired_text
        try:
            data = parse_json_payload(repaired_text)
            data = normalize_wrapped_schema_output(data, schema)
            validate_against_schema(data, schema, phase)
            if semantic_validator is not None:
                issues = semantic_validator(data)
                if issues:
                    last_issues = issues
                    raise ValueError(
                        f"{phase} JSON semantic validation failed after repair: {issues}"
                    )
            return data, current_session, True
        except Exception as exc:
            last_exc = exc
            if semantic_validator is not None and "data" in locals() and isinstance(data, dict):
                last_issues = semantic_validator(data)
            else:
                last_issues = []

    raise ValueError(f"Unable to parse valid {phase} JSON after retries: {last_exc}")
