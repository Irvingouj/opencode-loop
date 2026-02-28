from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

STATE_FILENAME = ".opencode-loop-state.json"
STATE_VERSION = 1


def default_state_path(cwd: str | None = None) -> Path:
    base = Path(cwd or os.getcwd())
    return base / STATE_FILENAME


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"State file must contain a JSON object: {path}")
    if data.get("version") != STATE_VERSION:
        raise ValueError(
            f"Unsupported state file version {data.get('version')} in {path}"
        )
    return data


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["version"] = STATE_VERSION

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)

    tmp_path.replace(path)
