import pytest

from opencode_loop.cli import parse_args
from opencode_loop.help_text import build_supervisor_help_text


def test_supervisor_help_text_mentions_resume_and_checks():
    text = build_supervisor_help_text()

    assert "opencode-loop supervisor guide" in text
    assert "--continue" in text
    assert "effective_checks" in text
    assert ".opencode-loop-state.json" in text


def test_parse_args_help_prints_supervisor_manual(capsys):
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--help"])

    captured = capsys.readouterr()
    assert excinfo.value.code == 0
    assert "What this tool is" in captured.out
    assert "Use `-h` or `--help-human`" in captured.out
