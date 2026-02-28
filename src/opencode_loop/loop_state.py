from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

LoopPhase = Literal["evaluator", "implementer", "done"]
LoopStatus = Literal["running", "completed", "max_iters"]


@dataclass(slots=True)
class PendingImplementerPayload:
    eval_json: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    next_task: str = ""
    recommended_checks: list[str] = field(default_factory=list)
    fix_plan: list[str] = field(default_factory=list)
    context_for_implementer: str = ""
    effective_checks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingImplementerPayload":
        return cls(
            eval_json=dict(data.get("eval_json", {})),
            reason=str(data.get("reason", "")),
            next_task=str(data.get("next_task", "")),
            recommended_checks=list(data.get("recommended_checks", [])),
            fix_plan=list(data.get("fix_plan", [])),
            context_for_implementer=str(data.get("context_for_implementer", "")),
            effective_checks=list(data.get("effective_checks", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_json": self.eval_json,
            "reason": self.reason,
            "next_task": self.next_task,
            "recommended_checks": self.recommended_checks,
            "fix_plan": self.fix_plan,
            "context_for_implementer": self.context_for_implementer,
            "effective_checks": self.effective_checks,
        }


@dataclass(slots=True)
class LoopConfig:
    goal: str
    done_criteria: str
    checks: list[str]
    prefix: str
    eval_template: str
    impl_template: str
    eval_schema: dict[str, Any]
    impl_schema: dict[str, Any]
    state_path: Path


@dataclass(slots=True)
class LoopRuntimeState:
    session_id: str = ""
    evaluator_has_run: bool = False
    last_action_json: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    next_iteration: int = 1
    resume_phase: LoopPhase = "evaluator"
    pending_implementer_payload: PendingImplementerPayload = field(
        default_factory=PendingImplementerPayload
    )
    resume_with_continue: bool = False
