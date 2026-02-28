from __future__ import annotations

import argparse
import shutil
import sys

from opencode_loop.config import (
    load_prompt_prefix,
    load_schema,
    load_template,
    resolve_checks,
    resolve_done_criteria,
    resolve_goal,
)
from opencode_loop.loop_state import LoopConfig, LoopRuntimeState
from opencode_loop.orchestrator import run_loop
from opencode_loop.prompts import DEFAULT_EVALUATOR_PROMPT, DEFAULT_IMPLEMENTER_PROMPT
from opencode_loop.resume import load_continue_context, save_loop_state
from opencode_loop.schemas import DEFAULT_EVALUATOR_SCHEMA, DEFAULT_IMPLEMENTER_SCHEMA
from opencode_loop.state import default_state_path
from opencode_loop.tui import console, print_startup_panel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenCode eval/execute loop")
    parser.add_argument(
        "-c",
        "--continue",
        dest="continue_run",
        action="store_true",
        help="Resume the last interrupted opencode-loop run",
    )
    parser.add_argument("--goal", help="High-level goal")
    parser.add_argument("--goal-file", help="File containing high-level goal text")
    parser.add_argument(
        "--done-criteria",
        default="All required functionality is implemented and verification checks pass.",
        help="Definition of done",
    )
    parser.add_argument(
        "--done-criteria-file", help="File containing definition-of-done text"
    )
    parser.add_argument("--model", help="OpenCode model, e.g. openai/gpt-5-mini")
    parser.add_argument("--agent", help="OpenCode agent profile")
    parser.add_argument("--max-iters", type=int, default=12, help="Max loop iterations")
    parser.add_argument(
        "--json-repair-attempts",
        type=int,
        default=3,
        help="Retries when output JSON is invalid",
    )
    parser.add_argument(
        "--max-effective-checks",
        type=int,
        default=5,
        help="Maximum effective checks passed into implementer prompts",
    )
    parser.add_argument(
        "--allowed-paths",
        default=".",
        help="Comma-separated allowlist for edits",
    )
    parser.add_argument(
        "--forbidden-changes",
        default="API contract changes, schema migrations, dependency upgrades unless explicitly required",
        help="Forbidden change list",
    )
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        help="Acceptance check command (repeatable)",
    )
    parser.add_argument(
        "--check-file",
        action="append",
        default=[],
        help="File with acceptance checks (one command per line; '#' comments allowed). Repeatable.",
    )
    parser.add_argument(
        "--system-prompt", default="", help="Prompt prefix injected into every turn"
    )
    parser.add_argument("--system-prompt-file", help="File containing prompt prefix")
    parser.add_argument("--session", help="Continue an existing OpenCode session id")
    parser.add_argument(
        "--evaluator-prompt-file", help="Template file for evaluator role prompt"
    )
    parser.add_argument(
        "--implementer-prompt-file", help="Template file for implementer role prompt"
    )
    parser.add_argument(
        "--evaluator-schema-file", help="Schema file for evaluator JSON output"
    )
    parser.add_argument(
        "--implementer-schema-file", help="Schema file for implementer JSON output"
    )
    parser.add_argument(
        "--no-pass-evaluator-json",
        action="store_true",
        help="Do not pass full evaluator JSON to implementer prompt",
    )
    return parser.parse_args()


def load_fresh_context(args: argparse.Namespace) -> tuple[LoopConfig, LoopRuntimeState]:
    config = LoopConfig(
        goal=resolve_goal(args),
        done_criteria=resolve_done_criteria(args),
        checks=resolve_checks(args),
        prefix=load_prompt_prefix(args),
        eval_template=load_template(
            args.evaluator_prompt_file, DEFAULT_EVALUATOR_PROMPT
        ),
        impl_template=load_template(
            args.implementer_prompt_file, DEFAULT_IMPLEMENTER_PROMPT
        ),
        eval_schema=load_schema(args.evaluator_schema_file, DEFAULT_EVALUATOR_SCHEMA),
        impl_schema=load_schema(
            args.implementer_schema_file, DEFAULT_IMPLEMENTER_SCHEMA
        ),
        state_path=default_state_path(),
    )
    runtime = LoopRuntimeState(session_id=args.session or "")
    return config, runtime


def main() -> int:
    args = parse_args()

    if not shutil.which("opencode"):
        console.print("[bold red]ERROR:[/bold red] 'opencode' not found in PATH")
        return 127

    try:
        if args.continue_run:
            config, runtime = load_continue_context(args, sys.argv[1:])
        else:
            config, runtime = load_fresh_context(args)
    except Exception as exc:
        console.print(f"[bold red]ERROR:[/bold red] {exc}")
        return 2

    print_startup_panel(args, config.goal, config.checks)
    if args.continue_run:
        console.print(
            f"[yellow]Resuming {runtime.resume_phase} at iteration {runtime.next_iteration} from {config.state_path}[/yellow]"
        )
    else:
        save_loop_state(args=args, config=config, runtime=runtime, status="running")

    return run_loop(args, config, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
