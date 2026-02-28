from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from typing import Any

from opencode_loop.config import (
    dedupe_keep_order,
    load_prompt_prefix,
    load_schema,
    load_template,
    resolve_checks,
    resolve_done_criteria,
    resolve_goal,
)
from opencode_loop.json_utils import parse_json_with_repair
from opencode_loop.prompts import DEFAULT_EVALUATOR_PROMPT, DEFAULT_IMPLEMENTER_PROMPT
from opencode_loop.runner import recover_empty_text_output, run_opencode
from opencode_loop.schemas import DEFAULT_EVALUATOR_SCHEMA, DEFAULT_IMPLEMENTER_SCHEMA
from opencode_loop.templates import (
    compose,
    list_to_bullets,
    render_template,
    schema_text,
)
from opencode_loop.tui import (
    console,
    print_eval_result,
    print_exec_result,
    print_run_summary,
    print_startup_panel,
    run_with_spinner,
)
from rich import box
from rich.panel import Panel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenCode eval/execute loop")
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

    parser.add_argument(
        "--verbose", action="store_true", help="Print full OpenCode text payloads"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not shutil.which("opencode"):
        console.print("[bold red]ERROR:[/bold red] 'opencode' not found in PATH")
        return 127

    try:
        goal = resolve_goal(args)
        done_criteria = resolve_done_criteria(args)
        checks = resolve_checks(args)
        eval_template = load_template(
            args.evaluator_prompt_file, DEFAULT_EVALUATOR_PROMPT
        )
        impl_template = load_template(
            args.implementer_prompt_file, DEFAULT_IMPLEMENTER_PROMPT
        )
        eval_schema = load_schema(args.evaluator_schema_file, DEFAULT_EVALUATOR_SCHEMA)
        impl_schema = load_schema(
            args.implementer_schema_file, DEFAULT_IMPLEMENTER_SCHEMA
        )
    except Exception as exc:
        console.print(f"[bold red]ERROR:[/bold red] {exc}")
        return 2

    print_startup_panel(args, goal, checks)

    prefix = load_prompt_prefix(args)
    session_id = args.session
    evaluator_has_run = False
    last_action_json: dict[str, Any] = {}
    history: list[dict[str, Any]] = []

    for i in range(1, args.max_iters + 1):
        console.rule(f"[bold]Iteration {i} / {args.max_iters}[/bold]", style="blue")

        eval_prompt = render_template(
            eval_template,
            {
                "GOAL": goal,
                "DONE_CRITERIA": done_criteria,
                "ALLOWED_PATHS": args.allowed_paths,
                "FORBIDDEN_CHANGES": args.forbidden_changes,
                "CHECKS_TEXT": list_to_bullets(checks),
                "ITERATION": str(i),
                "LAST_ACTION_JSON": json.dumps(
                    last_action_json, ensure_ascii=False, indent=2
                )
                if last_action_json
                else "{}",
                "OUTPUT_SCHEMA_TEXT": schema_text(eval_schema),
            },
        )
        eval_prompt = compose(prefix, eval_prompt)

        use_continue_eval = evaluator_has_run and not args.session
        console.log(f"[cyan]▶ EVALUATE[/cyan]  iter={i}")
        (eval_text, session_id), eval_elapsed = run_with_spinner(
            f"Evaluator  iter={i}",
            run_opencode,
            eval_prompt,
            args,
            session_id,
            use_continue=use_continue_eval,
            stream_label=f"iter{i}:eval",
            verbose=args.verbose,
        )
        evaluator_has_run = True

        if args.verbose:
            console.log(f"[dim][EVAL RAW][/dim]\n{eval_text}")
        if not eval_text.strip():
            try:
                eval_text, session_id = recover_empty_text_output(
                    args=args,
                    session_id=session_id,
                    phase="evaluator",
                    schema=eval_schema,
                    attempts=max(1, args.json_repair_attempts),
                    verbose=args.verbose,
                )
            except Exception as exc:
                console.print(f"[bold red]ERROR:[/bold red] {exc}")
                print_run_summary(history)
                return 2

        try:
            eval_json, session_id = parse_json_with_repair(
                eval_text,
                args,
                session_id,
                "evaluator",
                eval_schema,
                attempts=args.json_repair_attempts,
                use_continue_on_repair=True,
                verbose=args.verbose,
            )
        except Exception as exc:
            console.print(f"[bold red]ERROR:[/bold red] {exc}")
            print_run_summary(history)
            return 2

        is_done = bool(eval_json.get("is_done"))
        reason = str(eval_json.get("reason", ""))
        next_task = str(eval_json.get("next_task_prompt", "")).strip()
        recommended_checks = eval_json.get("recommended_checks", [])
        if not isinstance(recommended_checks, list):
            recommended_checks = []
        recommended_checks = [
            x for x in recommended_checks if isinstance(x, str) and x.strip()
        ]

        fix_plan = eval_json.get("fix_plan", [])
        if not isinstance(fix_plan, list):
            fix_plan = []
        fix_plan = [x for x in fix_plan if isinstance(x, str) and x.strip()]

        context_for_implementer = str(
            eval_json.get("context_for_implementer", "")
        ).strip()

        effective_checks = dedupe_keep_order(recommended_checks + checks)
        print_eval_result(
            i, is_done, reason, next_task, len(effective_checks), eval_elapsed
        )

        history.append(
            {
                "iter": i,
                "eval_elapsed": eval_elapsed,
                "exec_elapsed": None,
                "is_done": is_done,
                "reason": reason,
                "files_touched": [],
            }
        )

        if is_done:
            console.print(
                Panel(
                    f"[bold green]✔ Goal achieved[/bold green]\n{reason}",
                    border_style="green",
                    box=box.ROUNDED,
                )
            )
            print_run_summary(history)
            return 0
        if not next_task:
            console.print(
                "[bold red]ERROR:[/bold red] evaluator returned not-done but empty next_task_prompt"
            )
            print_run_summary(history)
            return 2

        if i > 2:
            has_file_ref = any(
                c in next_task
                for c in [".ts", ".js", ".py", ".json", "src/", "/routes/"]
            )
            if not has_file_ref:
                console.log(
                    "[yellow]⚠  Evaluator issued a check-only task with no file edits — possible spin loop[/yellow]"
                )

        console.log(f"[cyan]▶ EXECUTE[/cyan]   iter={i}")

        evaluator_json_for_impl = (
            json.dumps(eval_json, ensure_ascii=False, indent=2)
            if not args.no_pass_evaluator_json
            else "{}"
        )

        impl_prompt = render_template(
            impl_template,
            {
                "GOAL": goal,
                "DONE_CRITERIA": done_criteria,
                "ALLOWED_PATHS": args.allowed_paths,
                "FORBIDDEN_CHANGES": args.forbidden_changes,
                "CHECKS_TEXT": list_to_bullets(checks),
                "EFFECTIVE_CHECKS_TEXT": list_to_bullets(effective_checks),
                "EVALUATOR_JSON": evaluator_json_for_impl,
                "EVALUATOR_REASON": reason,
                "EVALUATOR_NEXT_TASK_PROMPT": next_task,
                "EVALUATOR_RECOMMENDED_CHECKS": list_to_bullets(recommended_checks),
                "EVALUATOR_FIX_PLAN_TEXT": list_to_bullets(fix_plan),
                "EVALUATOR_CONTEXT": context_for_implementer or "(none)",
                "OUTPUT_SCHEMA_TEXT": schema_text(impl_schema),
                "ITERATION": str(i),
            },
        )
        impl_prompt = compose(prefix, impl_prompt)

        (exec_text, session_id), exec_elapsed = run_with_spinner(
            f"Implementer iter={i}",
            run_opencode,
            impl_prompt,
            args,
            session_id,
            use_continue=False,
            stream_label=f"iter{i}:exec",
            verbose=args.verbose,
        )

        if args.verbose:
            console.log(f"[dim][EXEC RAW][/dim]\n{exec_text}")
        if not exec_text.strip():
            try:
                exec_text, session_id = recover_empty_text_output(
                    args=args,
                    session_id=session_id,
                    phase="implementer",
                    schema=impl_schema,
                    attempts=max(1, args.json_repair_attempts),
                    verbose=args.verbose,
                )
            except Exception as exc:
                console.print(f"[bold red]ERROR:[/bold red] {exc}")
                print_run_summary(history)
                return 2

        try:
            exec_json, session_id = parse_json_with_repair(
                exec_text,
                args,
                session_id,
                "implementer",
                impl_schema,
                attempts=args.json_repair_attempts,
                use_continue_on_repair=False,
                verbose=args.verbose,
            )
        except Exception as exc:
            console.print(f"[bold red]ERROR:[/bold red] {exc}")
            print_run_summary(history)
            return 2

        summary = str(exec_json.get("summary", "")).strip()
        files_touched = exec_json.get("files_touched", [])
        if not isinstance(files_touched, list):
            files_touched = []

        print_exec_result(i, summary, files_touched, exec_elapsed)

        if history:
            history[-1]["exec_elapsed"] = exec_elapsed
            history[-1]["files_touched"] = files_touched

        last_action_json = exec_json

    console.print(
        Panel(
            f"[bold red]✘ Max iterations reached ({args.max_iters}) without done=true[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        )
    )
    print_run_summary(history)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
