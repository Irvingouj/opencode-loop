from pathlib import Path

from opencode_loop.state import STATE_FILENAME, default_state_path, load_state, save_state


def test_default_state_path_uses_cwd(tmp_path: Path):
    path = default_state_path(str(tmp_path))

    assert path == tmp_path / STATE_FILENAME


def test_save_and_load_state_round_trip(tmp_path: Path):
    path = tmp_path / STATE_FILENAME

    save_state(path, {"status": "running", "next_iteration": 2})
    loaded = load_state(path)

    assert loaded["status"] == "running"
    assert loaded["next_iteration"] == 2
    assert loaded["version"] == 1
