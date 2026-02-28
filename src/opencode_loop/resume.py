from __future__ import annotations

from typing import Any

from opencode_loop.loop_state import (
    LoopConfig,
    LoopRuntimeState,
    PendingImplementerPayload,
)
from opencode_loop.prompts import DEFAULT_EVALUATOR_PROMPT, DEFAULT_IMPLEMENTER_PROMPT
from opencode_loop.schemas import DEFAULT_EVALUATOR_SCHEMA, DEFAULT_IMPLEMENTER_SCHEMA
from opencode_loop.state import default_state_path, load_state, save_state


def ensure_continue_args_are_clean(argv: list[str]) -> None:
    allowed = {"--continue", "-c"}
    extras = [arg for arg in argv if arg not in allowed]
    if extras:
        raise ValueError(
            f"--continue only supports resuming the last run; unexpected arguments: {' '.join(extras)}"
        )


def save_loop_state(
    *,
    args,
    config: LoopConfig,
    runtime: LoopRuntimeState,
    status: str,
) -> None:
    save_state(
        config.state_path,
        {
            "status": status,
            "phase": runtime.resume_phase,
            "next_iteration": runtime.next_iteration,
            "session_id": runtime.session_id,
            "goal": config.goal,
            "done_criteria": config.done_criteria,
            "checks": config.checks,
            "prompt_prefix": config.prefix,
            "eval_template": config.eval_template,
            "impl_template": config.impl_template,
            "eval_schema": config.eval_schema,
            "impl_schema": config.impl_schema,
            "evaluator_has_run": runtime.evaluator_has_run,
            "history": runtime.history,
            "last_action_json": runtime.last_action_json,
            "pending_implementer_payload": runtime.pending_implementer_payload.to_dict(),
            "model": args.model,
            "agent": args.agent,
            "allowed_paths": args.allowed_paths,
            "forbidden_changes": args.forbidden_changes,
            "no_pass_evaluator_json": args.no_pass_evaluator_json,
            "max_iters": args.max_iters,
            "json_repair_attempts": args.json_repair_attempts,
            "max_effective_checks": args.max_effective_checks,
        },
    )


def load_continue_context(args, argv: list[str]) -> tuple[LoopConfig, LoopRuntimeState]:
    ensure_continue_args_are_clean(argv)
    state_path = default_state_path()
    state = load_state(state_path)
    if state.get("status") == "completed":
        raise ValueError(f"Last run already completed: {state_path}")

    args.model = state.get("model")
    args.agent = state.get("agent")
    args.allowed_paths = str(state.get("allowed_paths", "."))
    args.forbidden_changes = str(state.get("forbidden_changes", ""))
    args.no_pass_evaluator_json = bool(state.get("no_pass_evaluator_json", False))
    args.max_iters = int(state.get("max_iters", args.max_iters))
    args.json_repair_attempts = int(
        state.get("json_repair_attempts", args.json_repair_attempts)
    )
    args.max_effective_checks = int(
        state.get("max_effective_checks", args.max_effective_checks)
    )
    args.session = str(state.get("session_id", ""))

    config = LoopConfig(
        goal=str(state.get("goal", "")),
        done_criteria=str(state.get("done_criteria", "")),
        checks=list(state.get("checks", [])),
        prefix=str(state.get("prompt_prefix", "")),
        eval_template=str(state.get("eval_template", DEFAULT_EVALUATOR_PROMPT)),
        impl_template=str(state.get("impl_template", DEFAULT_IMPLEMENTER_PROMPT)),
        eval_schema=dict(state.get("eval_schema", DEFAULT_EVALUATOR_SCHEMA)),
        impl_schema=dict(state.get("impl_schema", DEFAULT_IMPLEMENTER_SCHEMA)),
        state_path=state_path,
    )
    runtime = LoopRuntimeState(
        session_id=str(state.get("session_id", "")),
        evaluator_has_run=bool(state.get("evaluator_has_run", False)),
        last_action_json=dict(state.get("last_action_json", {})),
        history=list(state.get("history", [])),
        next_iteration=int(state.get("next_iteration", 1)),
        resume_phase=str(state.get("phase", "evaluator")),
        pending_implementer_payload=PendingImplementerPayload.from_dict(
            dict(state.get("pending_implementer_payload", {}))
        ),
        resume_with_continue=True,
    )
    return config, runtime
