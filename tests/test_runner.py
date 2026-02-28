from types import SimpleNamespace

from opencode_loop.runner import build_opencode_cmd


def test_build_opencode_cmd_enables_json_streaming_and_thinking():
    args = SimpleNamespace(model=None, agent=None)

    cmd = build_opencode_cmd("hello", args, None, False)

    assert cmd[:5] == ["opencode", "run", "--format", "json", "--thinking"]
    assert cmd[-1] == "hello"


def test_build_opencode_cmd_uses_session_when_present():
    args = SimpleNamespace(model="openai/gpt-5-mini", agent="builder")

    cmd = build_opencode_cmd("hello", args, "ses_123", False)

    assert "--model" in cmd
    assert "--agent" in cmd
    assert "--session" in cmd
    assert "-c" not in cmd


def test_build_opencode_cmd_prefers_continue_over_session():
    args = SimpleNamespace(model=None, agent=None)

    cmd = build_opencode_cmd("hello", args, "ses_123", True)

    assert "-c" in cmd
    assert "--session" not in cmd
