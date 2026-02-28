from __future__ import annotations

import json
import subprocess
from typing import Any

from opencode_loop.tui import _stream_event_line, console
from opencode_loop.templates import schema_text


def run_opencode(
    message: str,
    args,
    session_id: str | None,
    use_continue: bool = False,
    stream_label: str = "opencode",
    verbose: bool = False,
) -> tuple[str, str]:
    cmd = ["opencode", "run", "--format", "json"]
    if args.model:
        cmd += ["--model", args.model]
    if args.agent:
        cmd += ["--agent", args.agent]
    if use_continue:
        cmd += ["-c"]
    elif session_id:
        cmd += ["--session", session_id]
    cmd.append(message)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None

    raw_lines: list[str] = []
    texts: list[str] = []
    sid: str | None = None
    stream_state: dict[str, Any] = {"step_no": 0, "in_step": False}

    for line in proc.stdout:
        raw_lines.append(line)
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue

        sid_line = obj.get("sessionID")
        if isinstance(sid_line, str) and sid_line:
            sid = sid_line

        _stream_event_line(stream_label, obj, stream_state, verbose)

        if obj.get("type") == "text":
            part = obj.get("part", {}) if isinstance(obj.get("part"), dict) else {}
            txt = part.get("text")
            if isinstance(txt, str):
                texts.append(txt)

    return_code = proc.wait()
    raw_output = "".join(raw_lines)
    if return_code != 0:
        raise RuntimeError(f"OpenCode failed ({return_code}):\n{raw_output}")
    text = "\n".join(texts).strip()
    return text, sid or (session_id or "")


def recover_empty_text_output(
    *,
    args,
    session_id: str,
    phase: str,
    schema: dict[str, Any],
    attempts: int,
    verbose: bool = False,
) -> tuple[str, str]:
    current_session = session_id
    for n in range(1, attempts + 1):
        console.log(
            f"[yellow]⚠ {phase} returned empty output — requesting continue ({n}/{attempts})[/yellow]"
        )
        prompt = (
            "Continue and finish your task.\n"
            "If you are not finished, finish it first.\n"
            "If already finished, return ONLY the final JSON now.\n"
            "Do not return markdown/code fences/commentary.\n"
            "Do NOT wrap output inside keys like 'required'/'optional'.\n"
            "Return one top-level payload object that matches this schema exactly:\n"
            f"{schema_text(schema)}"
        )
        text, current_session = run_opencode(
            prompt,
            args,
            current_session,
            use_continue=True,
            stream_label=f"{phase}:continue#{n}",
            verbose=verbose,
        )
        if text.strip():
            return text, current_session
    raise ValueError(
        f"{phase} returned no text output after continue retries ({attempts})"
    )
