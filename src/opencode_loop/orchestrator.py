from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from rich import box
from rich.panel import Panel

from opencode_loop.config import dedupe_keep_order
from opencode_loop.json_utils import parse_json_with_repair
from opencode_loop.loop_state import (
    LoopConfig,
    LoopRuntimeState,
    PendingImplementerPayload,
)
from opencode_loop.resume import save_loop_state
from opencode_loop.runner import recover_empty_text_output, run_opencode
from opencode_loop.templates import compose, list_to_bullets, render_template, schema_text
from opencode_loop.tui import (
    console,
    print_eval_result,
    print_exec_result,
    print_run_summary,
    run_with_spinner,
)


@dataclass(slots=True)
class EvalStepResult:
    eval_json: dict[str, Any]
    is_done: bool
    reason: str
    next_task: str
    recommended_checks: list[str]
    fix_plan: list[str]
    context_for_implementer: str
    effective_checks: list[str]
    eval_elapsed: float


def evaluator_semantic_issues(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    is_done = data.get("is_done")
    next_task = data.get("next_task_prompt")

    if is_done is False:
        if not isinstance(next_task, str) or not next_task.strip():
            issues.append(
                "is_done was false but next_task_prompt was missing or empty"
            )

    return issues


def clamp_effective_checks(
    recommended_checks: list[str],
    checks: list[str],
    *,
    recovered: bool,
    max_effective_checks: int,
) -> list[str]:
    if recovered:
        return dedupe_keep_order(checks)[:max_effective_checks]
    return dedupe_keep_order(recommended_checks + checks)[:max_effective_checks]


def build_evaluator_prompt(config: LoopConfig, args, iteration: int, last_action_json: dict[str, Any]) -> str:
    prompt = render_template(
        config.eval_template,
        {
            "GOAL": config.goal,
            "DONE_CRITERIA": config.done_criteria,
            "ALLOWED_PATHS": args.allowed_paths,
            "FORBIDDEN_CHANGES": args.forbidden_changes,
            "CHECKS_TEXT": list_to_bullets(config.checks),
            "ITERATION": str(iteration),
            "LAST_ACTION_JSON": json.dumps(last_action_json, ensure_ascii=False, indent=2)
            if last_action_json
            else "{}",
            "OUTPUT_SCHEMA_TEXT": schema_text(config.eval_schema),
        },
    )
    return compose(config.prefix, prompt)


def build_implementer_prompt(
    config: LoopConfig,
    args,
    iteration: int,
    eval_result: EvalStepResult,
) -> str:
    evaluator_json_for_impl = (
        json.dumps(eval_result.eval_json, ensure_ascii=False, indent=2)
        if not args.no_pass_evaluator_json
        else "{}"
    )
    prompt = render_template(
        config.impl_template,
        {
            "GOAL": config.goal,
            "DONE_CRITERIA": config.done_criteria,
            "ALLOWED_PATHS": args.allowed_paths,
            "FORBIDDEN_CHANGES": args.forbidden_changes,
            "CHECKS_TEXT": list_to_bullets(config.checks),
            "EFFECTIVE_CHECKS_TEXT": list_to_bullets(eval_result.effective_checks),
            "EVALUATOR_JSON": evaluator_json_for_impl,
            "EVALUATOR_REASON": eval_result.reason,
            "EVALUATOR_NEXT_TASK_PROMPT": eval_result.next_task,
            "EVALUATOR_RECOMMENDED_CHECKS": list_to_bullets(
                eval_result.recommended_checks
            ),
            "EVALUATOR_FIX_PLAN_TEXT": list_to_bullets(eval_result.fix_plan),
            "EVALUATOR_CONTEXT": eval_result.context_for_implementer or "(none)",
            "OUTPUT_SCHEMA_TEXT": schema_text(config.impl_schema),
            "ITERATION": str(iteration),
        },
    )
    return compose(config.prefix, prompt)


def _parse_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def run_evaluator_step(
    *,
    args,
    config: LoopConfig,
    runtime: LoopRuntimeState,
    iteration: int,
) -> EvalStepResult:
    eval_prompt = build_evaluator_prompt(config, args, iteration, runtime.last_action_json)
    use_continue_eval = runtime.resume_with_continue or (
        runtime.evaluator_has_run and not args.session
    )
    console.log(f"[cyan]▶ EVALUATE[/cyan]  iter={iteration}")
    (eval_text, runtime.session_id), eval_elapsed = run_with_spinner(
        f"Evaluator  iter={iteration}",
        run_opencode,
        eval_prompt,
        args,
        runtime.session_id,
        use_continue=use_continue_eval,
        stream_label=f"iter{iteration}:eval",
    )
    runtime.resume_with_continue = False
    runtime.evaluator_has_run = True

    console.log(f"[dim][EVAL RAW][/dim]\n{eval_text}")
    if not eval_text.strip():
        eval_text, runtime.session_id = recover_empty_text_output(
            args=args,
            session_id=runtime.session_id,
            phase="evaluator",
            schema=config.eval_schema,
            attempts=max(1, args.json_repair_attempts),
        )

    eval_json, runtime.session_id, eval_recovered = parse_json_with_repair(
        eval_text,
        args,
        runtime.session_id,
        "evaluator",
        config.eval_schema,
        attempts=args.json_repair_attempts,
        use_continue_on_repair=True,
        semantic_validator=evaluator_semantic_issues,
    )

    is_done = bool(eval_json.get("is_done"))
    reason = str(eval_json.get("reason", ""))
    next_task = str(eval_json.get("next_task_prompt", "")).strip()
    recommended_checks = _parse_string_list(eval_json.get("recommended_checks", []))
    fix_plan = _parse_string_list(eval_json.get("fix_plan", []))
    context_for_implementer = str(eval_json.get("context_for_implementer", "")).strip()

    effective_checks = clamp_effective_checks(
        recommended_checks,
        config.checks,
        recovered=eval_recovered,
        max_effective_checks=max(0, args.max_effective_checks),
    )
    if eval_recovered:
        recommended_checks = []
        console.print(
            "[yellow]Evaluator recovered; resetting effective checks to base checks for this iteration.[/yellow]"
        )

    print_eval_result(
        iteration, is_done, reason, next_task, len(effective_checks), eval_elapsed
    )

    runtime.history.append(
        {
            "iter": iteration,
            "eval_elapsed": eval_elapsed,
            "exec_elapsed": None,
            "is_done": is_done,
            "reason": reason,
            "files_touched": [],
        }
    )
    return EvalStepResult(
        eval_json=eval_json,
        is_done=is_done,
        reason=reason,
        next_task=next_task,
        recommended_checks=recommended_checks,
        fix_plan=fix_plan,
        context_for_implementer=context_for_implementer,
        effective_checks=effective_checks,
        eval_elapsed=eval_elapsed,
    )


def eval_result_from_pending(payload: PendingImplementerPayload) -> EvalStepResult:
    return EvalStepResult(
        eval_json=payload.eval_json,
        is_done=False,
        reason=payload.reason,
        next_task=payload.next_task,
        recommended_checks=payload.recommended_checks,
        fix_plan=payload.fix_plan,
        context_for_implementer=payload.context_for_implementer,
        effective_checks=payload.effective_checks,
        eval_elapsed=0.0,
    )


def handle_eval_outcome(
    *,
    args,
    config: LoopConfig,
    runtime: LoopRuntimeState,
    iteration: int,
    eval_result: EvalStepResult,
) -> int | None:
    if eval_result.is_done:
        runtime.resume_phase = "done"
        save_loop_state(args=args, config=config, runtime=runtime, status="completed")
        console.print(
            Panel(
                f"[bold green]✔ Goal achieved[/bold green]\n{eval_result.reason}",
                border_style="green",
                box=box.ROUNDED,
            )
        )
        print_run_summary(runtime.history)
        return 0

    if not eval_result.next_task:
        console.print(
            "[bold red]ERROR:[/bold red] evaluator returned not-done but empty next_task_prompt"
        )
        print_run_summary(runtime.history)
        return 2

    if iteration > 2:
        has_file_ref = any(
            needle in eval_result.next_task
            for needle in [".ts", ".js", ".py", ".json", "src/", "/routes/"]
        )
        if not has_file_ref:
            console.log(
                "[yellow]⚠  Evaluator issued a check-only task with no file edits — possible spin loop[/yellow]"
            )

    runtime.resume_phase = "implementer"
    runtime.next_iteration = iteration
    runtime.pending_implementer_payload = PendingImplementerPayload(
        eval_json=eval_result.eval_json,
        reason=eval_result.reason,
        next_task=eval_result.next_task,
        recommended_checks=eval_result.recommended_checks,
        fix_plan=eval_result.fix_plan,
        context_for_implementer=eval_result.context_for_implementer,
        effective_checks=eval_result.effective_checks,
    )
    save_loop_state(args=args, config=config, runtime=runtime, status="running")
    return None


def run_implementer_step(
    *,
    args,
    config: LoopConfig,
    runtime: LoopRuntimeState,
    iteration: int,
    eval_result: EvalStepResult,
) -> None:
    console.log(f"[cyan]▶ EXECUTE[/cyan]   iter={iteration}")
    impl_prompt = build_implementer_prompt(config, args, iteration, eval_result)
    (exec_text, runtime.session_id), exec_elapsed = run_with_spinner(
        f"Implementer iter={iteration}",
        run_opencode,
        impl_prompt,
        args,
        runtime.session_id,
        use_continue=runtime.resume_with_continue or runtime.resume_phase == "implementer",
        stream_label=f"iter{iteration}:exec",
    )
    runtime.resume_with_continue = False

    console.log(f"[dim][EXEC RAW][/dim]\n{exec_text}")
    if not exec_text.strip():
        exec_text, runtime.session_id = recover_empty_text_output(
            args=args,
            session_id=runtime.session_id,
            phase="implementer",
            schema=config.impl_schema,
            attempts=max(1, args.json_repair_attempts),
        )

    exec_json, runtime.session_id, _ = parse_json_with_repair(
        exec_text,
        args,
        runtime.session_id,
        "implementer",
        config.impl_schema,
        attempts=args.json_repair_attempts,
        use_continue_on_repair=True,
    )

    summary = str(exec_json.get("summary", "")).strip()
    files_touched = exec_json.get("files_touched", [])
    if not isinstance(files_touched, list):
        files_touched = []

    print_exec_result(iteration, summary, files_touched, exec_elapsed)
    if runtime.history:
        runtime.history[-1]["exec_elapsed"] = exec_elapsed
        runtime.history[-1]["files_touched"] = files_touched

    runtime.last_action_json = exec_json
    runtime.resume_phase = "evaluator"
    runtime.next_iteration = iteration + 1
    runtime.pending_implementer_payload = PendingImplementerPayload()
    save_loop_state(args=args, config=config, runtime=runtime, status="running")


def run_loop(args, config: LoopConfig, runtime: LoopRuntimeState) -> int:
    for iteration in range(runtime.next_iteration, args.max_iters + 1):
        console.rule(f"[bold]Iteration {iteration} / {args.max_iters}[/bold]", style="blue")

        if runtime.resume_phase == "implementer":
            if not runtime.pending_implementer_payload.next_task:
                console.print(
                    "[bold red]ERROR:[/bold red] continue state is missing pending implementer payload"
                )
                print_run_summary(runtime.history)
                return 2
            console.print(
                f"[yellow]Skipping evaluator; resuming pending implementer for iteration {iteration}.[/yellow]"
            )
            eval_result = eval_result_from_pending(runtime.pending_implementer_payload)
        else:
            try:
                eval_result = run_evaluator_step(
                    args=args,
                    config=config,
                    runtime=runtime,
                    iteration=iteration,
                )
            except Exception as exc:
                console.print(f"[bold red]ERROR:[/bold red] {exc}")
                print_run_summary(runtime.history)
                return 2

            outcome = handle_eval_outcome(
                args=args,
                config=config,
                runtime=runtime,
                iteration=iteration,
                eval_result=eval_result,
            )
            if outcome is not None:
                return outcome

        try:
            run_implementer_step(
                args=args,
                config=config,
                runtime=runtime,
                iteration=iteration,
                eval_result=eval_result,
            )
        except Exception as exc:
            console.print(f"[bold red]ERROR:[/bold red] {exc}")
            print_run_summary(runtime.history)
            return 2

    console.print(
        Panel(
            f"[bold red]✘ Max iterations reached ({args.max_iters}) without done=true[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        )
    )
    runtime.resume_phase = "evaluator"
    runtime.next_iteration = args.max_iters
    save_loop_state(args=args, config=config, runtime=runtime, status="max_iters")
    print_run_summary(runtime.history)
    return 3
