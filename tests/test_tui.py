from opencode_loop.tui import _tool_input_summary, _tool_output_lines


def test_tool_input_summary_compacts_tool_input():
    summary = _tool_input_summary({"input": {"filePath": "/tmp/demo.txt", "limit": 20}})

    assert "filePath" in summary
    assert "/tmp/demo.txt" in summary


def test_tool_output_lines_prefers_metadata_preview():
    lines = _tool_output_lines(
        {
            "output": "full output should not win",
            "metadata": {"preview": "line 1\nline 2\nline 3"},
        }
    )

    assert lines == ["line 1", "line 2", "line 3"]


def test_tool_output_lines_falls_back_to_output_text():
    lines = _tool_output_lines({"output": "alpha\nbeta\ngamma\ndelta\nepsilon"})

    assert lines == ["alpha", "beta", "gamma", "delta"]
