DEFAULT_EVALUATOR_SCHEMA = {
    "required": {"is_done": "bool", "reason": "str"},
    "optional": {
        "next_task_prompt": "str",
        "recommended_checks": "list[str]",
        "fix_plan": "list[str]",
        "context_for_implementer": "str",
    },
}


DEFAULT_IMPLEMENTER_SCHEMA = {
    "required": {
        "summary": "str",
        "files_touched": "list[str]",
        "checks": "list[object]",
    },
    "optional": {
        "risks": "list[str]",
        "open_issues": "list[str]",
    },
}
