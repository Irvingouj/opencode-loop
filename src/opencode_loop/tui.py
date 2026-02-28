from __future__ import annotations

import json
import os
import time
from typing import Any

from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from opencode_loop.templates import _compact_json, _pick_first_str

console = Console(highlight=False, log_path=False)


def _emit(message: str = "") -> None:
    console.print(message)


def _truncate(value: str, limit: int = 160) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _shorten_path_text(value: str) -> str:
    text = value.strip()
    if not text:
        return text

    cwd = os.getcwd()
    if text.startswith(cwd + os.sep):
        return os.path.relpath(text, cwd)
    return text


def _summarize_mapping(value: dict[str, Any]) -> str:
    preferred_keys = [
        "filePath",
        "path",
        "pattern",
        "command",
        "tool",
        "name",
        "status",
    ]
    bits: list[str] = []
    seen: set[str] = set()

    for key in preferred_keys:
        if key not in value:
            continue
        seen.add(key)
        rendered = _compact_value(value[key], 80)
        bits.append(f"{key}={rendered}")

    for key, item in value.items():
        if key in seen:
            continue
        bits.append(f"{key}={_compact_value(item, 80)}")
        if len(bits) >= 4:
            break

    return ", ".join(bits) if bits else _compact_json(value)


def _compact_value(value: Any, limit: int = 160) -> str:
    if isinstance(value, str):
        return _truncate(_shorten_path_text(value), limit)
    if isinstance(value, dict):
        return _truncate(_summarize_mapping(value), limit)
    if isinstance(value, list):
        rendered_items = [_compact_value(item, 48) for item in value[:4]]
        if len(value) > 4:
            rendered_items.append("…")
        return _truncate(", ".join(rendered_items), limit)
    return _truncate(_compact_json(value), limit)


def _tool_input_summary(state: dict[str, Any]) -> str:
    input_value = state.get("input")
    if input_value is None:
        return ""
    return _compact_value(input_value)


def _tool_output_lines(state: dict[str, Any], max_lines: int = 4) -> list[str]:
    metadata = state.get("metadata")
    if isinstance(metadata, dict):
        preview = metadata.get("preview")
        if isinstance(preview, str) and preview.strip():
            return [
                _compact_value(line, 180) for line in preview.strip().splitlines()[:max_lines]
            ]

    output = state.get("output")
    if isinstance(output, str) and output.strip():
        lines = [_compact_value(line, 180) for line in output.strip().splitlines()[:max_lines]]
        if all("/" in line for line in lines):
            return [", ".join(line.rsplit("/", 1)[-1] for line in lines)]
        return lines
    if output is None:
        return []
    return [_compact_value(output, 180)]


def _human_event_summary(obj: dict[str, Any]) -> str:
    typ = str(obj.get("type", ""))
    part = obj.get("part", {}) if isinstance(obj.get("part"), dict) else {}

    reason = _pick_first_str(part, ["reason", "status"])
    ptype = _pick_first_str(part, ["type"])
    name = _pick_first_str(part, ["name", "toolName", "tool", "command"])
    msg = _pick_first_str(part, ["message", "title", "summary"])

    bits: list[str] = [f"type={typ}"]
    if ptype:
        bits.append(f"part={ptype}")
    if name:
        bits.append(f"name={name}")
    if reason:
        bits.append(f"reason={reason}")
    if msg:
        bits.append(f"msg={msg}")

    if len(bits) <= 1:
        bits.append(f"data={_compact_json(obj)}")
    return " ".join(bits)


def _stream_event_line(label: str, obj: dict[str, Any], state: dict[str, Any]) -> None:
    typ = str(obj.get("type", ""))
    part = obj.get("part", {}) if isinstance(obj.get("part"), dict) else {}
    step_no = int(state.get("step_no", 0))
    phase = label.split(":", 1)[-1] if ":" in label else label
    phase_title = phase.upper()

    if typ == "step_start":
        next_step = step_no + 1
        state["step_no"] = next_step
        state["in_step"] = True
        state["step_tool"] = None
        _emit(f"[bold cyan]{phase_title}[/bold cyan] step {next_step}")
        return

    if typ == "tool_use":
        name = _pick_first_str(part, ["name", "toolName", "tool"]) or "unknown-tool"
        tool_state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
        status = _pick_first_str(tool_state, ["status"]) or "unknown"
        state["step_tool"] = name
        _emit(f"  tool [cyan]{name}[/cyan]  [bold]{status}[/bold]")
        input_summary = _tool_input_summary(tool_state)
        if input_summary:
            _emit(f"    in : [dim]{input_summary}[/dim]")
        for line in _tool_output_lines(tool_state):
            _emit(f"    out: [dim]{line}[/dim]")
        return

    if typ == "step_finish":
        reason = part.get("reason", "")
        tokens = part.get("tokens", {}) if isinstance(part.get("tokens"), dict) else {}
        token_bits: list[str] = []
        for key in ["input", "output", "reasoning", "total"]:
            value = tokens.get(key)
            if isinstance(value, int):
                token_bits.append(f"{key}={value}")
        token_suffix = f"  [dim]{' '.join(token_bits)}[/dim]" if token_bits else ""
        reason_text = reason or "unknown"
        _emit(f"  done: {reason_text}{token_suffix}")
        state["in_step"] = False
        return

    if typ == "reasoning":
        txt = part.get("text", "")
        if isinstance(txt, str) and txt.strip():
            _emit(f"  think: [dim]{_truncate(txt, 180)}[/dim]")
        return

    if typ == "text":
        txt = part.get("text", "")
        if isinstance(txt, str) and txt:
            lines = txt.splitlines() or [txt]
            for ln in lines:
                rendered = ln if ln.strip() else " "
                _emit(f"  text: {rendered}")
        return

    _emit(f"  [dim]{_human_event_summary(obj)}[/dim]")


def print_startup_panel(args, goal: str, checks: list[str]) -> None:
    lines = [
        f"[bold]Goal:[/bold] {goal[:120]}{'…' if len(goal) > 120 else ''}",
        f"[bold]Model:[/bold] {args.model or '(default)'}  "
        f"[bold]Agent:[/bold] {args.agent or '(default)'}  "
        f"[bold]Max iters:[/bold] {args.max_iters}",
        f"[bold]Session:[/bold] {args.session or '(new)'}",
        f"[bold]Checks:[/bold] {len(checks)} loaded",
    ]
    for attr, label in [
        ("system_prompt_file", "System prompt"),
        ("goal_file", "Goal file"),
        ("done_criteria_file", "Done criteria"),
        ("evaluator_prompt_file", "Evaluator prompt"),
        ("implementer_prompt_file", "Implementer prompt"),
    ]:
        val = getattr(args, attr, None)
        if val:
            lines.append(f"[bold]{label}:[/bold] {val}")
    if args.check_file:
        lines.append(f"[bold]Check files:[/bold] {', '.join(args.check_file)}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold cyan]opencode_loop[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )


def print_eval_result(
    i: int,
    is_done: bool,
    reason: str,
    next_task: str,
    checks_count: int,
    elapsed: float,
) -> None:
    status_icon = (
        "[bold green]✔ DONE[/bold green]"
        if is_done
        else "[bold yellow]→ CONTINUE[/bold yellow]"
    )
    _emit(f"Evaluator result  {status_icon}  ({elapsed:.1f}s)")
    _emit(f"  [italic]{reason}[/italic]")
    if not is_done and next_task:
        first_line = next_task.split("\n")[0].strip()
        _emit(
            f"  [bold]Next task:[/bold] {first_line[:140]}{'…' if len(first_line) > 140 or chr(10) in next_task else ''}"
        )
    if checks_count:
        _emit(f"  [dim]Effective checks: {checks_count}[/dim]")


def print_exec_result(
    i: int, summary: str, files_touched: list[str], elapsed: float
) -> None:
    _emit(f"Implementer result  [bold green]✔[/bold green]  ({elapsed:.1f}s)")
    if summary:
        _emit(f"  [italic]{summary[:200]}[/italic]")
    if files_touched:
        for f in files_touched:
            _emit(f"  [dim cyan]touched:[/dim cyan] {_shorten_path_text(f)}")


def print_run_summary(history: list[dict[str, Any]]) -> None:
    t = Table(title="Run Summary", box=box.SIMPLE_HEAVY, show_lines=False)
    t.add_column("Iter", style="bold", width=5)
    t.add_column("Eval (s)", justify="right", width=9)
    t.add_column("Exec (s)", justify="right", width=9)
    t.add_column("Files", width=8, justify="right")
    t.add_column("Status", width=10)
    t.add_column("Reason", no_wrap=False)

    for row in history:
        status = "[green]done[/green]" if row["is_done"] else "[yellow]→[/yellow]"
        exec_s = (
            f"{row['exec_elapsed']:.1f}" if row.get("exec_elapsed") is not None else "—"
        )
        t.add_row(
            str(row["iter"]),
            f"{row['eval_elapsed']:.1f}",
            exec_s,
            str(len(row.get("files_touched", []))),
            status,
            row.get("reason", "")[:80],
        )
    console.print(t)


def run_with_spinner(label: str, fn, *args, **kwargs) -> tuple[Any, float]:
    start = time.time()
    result = None
    exc = None

    with Live(
        Spinner("dots", text=Text(f"{label}…", style="cyan")),
        console=console,
        refresh_per_second=10,
        transient=True,
    ):
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            exc = e

    elapsed = time.time() - start
    if exc is not None:
        raise exc
    return result, elapsed
