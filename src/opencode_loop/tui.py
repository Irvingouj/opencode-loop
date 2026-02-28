from __future__ import annotations

import json
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

console = Console(highlight=False)


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


def _stream_event_line(
    label: str, obj: dict[str, Any], state: dict[str, Any], verbose: bool
) -> None:
    typ = str(obj.get("type", ""))
    part = obj.get("part", {}) if isinstance(obj.get("part"), dict) else {}
    step_no = int(state.get("step_no", 0))

    if typ == "step_start":
        state["step_no"] = step_no + 1
        state["in_step"] = True
        state["step_tool"] = None
        return

    if typ == "tool_use":
        name = _pick_first_str(part, ["name", "toolName", "tool"])
        state["step_tool"] = name
        n = state.get("step_no", "?")
        console.log(f"  [dim]{label}[/dim]  step {n} · [cyan]{name}[/cyan]")
        return

    if typ == "step_finish":
        reason = part.get("reason", "")
        if reason == "stop":
            n = state.get("step_no", "?")
            console.log(f"  [dim]{label}[/dim]  step {n} · [dim]↩ stop[/dim]")
        state["in_step"] = False
        return

    if typ == "text":
        if verbose:
            txt = part.get("text", "")
            if txt.strip():
                for ln in txt.strip().splitlines():
                    console.log(f"  [dim]{label} {ln}[/dim]")
        return

    if verbose:
        console.log(f"[dim]{label} {_human_event_summary(obj)}[/dim]")


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
    console.log(f"Evaluator result  {status_icon}  ({elapsed:.1f}s)")
    console.log(f"  [italic]{reason}[/italic]")
    if not is_done and next_task:
        first_line = next_task.split("\n")[0].strip()
        console.log(
            f"  [bold]Next task:[/bold] {first_line[:140]}{'…' if len(first_line) > 140 or chr(10) in next_task else ''}"
        )
    if checks_count:
        console.log(f"  [dim]Effective checks: {checks_count}[/dim]")


def print_exec_result(
    i: int, summary: str, files_touched: list[str], elapsed: float
) -> None:
    console.log(f"Implementer result  [bold green]✔[/bold green]  ({elapsed:.1f}s)")
    if summary:
        console.log(f"  [italic]{summary[:200]}[/italic]")
    if files_touched:
        for f in files_touched:
            console.log(f"  [dim cyan]  touched:[/dim cyan] {f}")


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
