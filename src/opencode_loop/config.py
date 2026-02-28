from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_text_file(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8").strip()


def load_prompt_prefix(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.system_prompt:
        parts.append(args.system_prompt.strip())
    if args.system_prompt_file:
        parts.append(load_text_file(args.system_prompt_file))
    return "\n\n".join(p for p in parts if p)


def resolve_goal(args: argparse.Namespace) -> str:
    goal = (args.goal or "").strip()
    if args.goal_file:
        goal = load_text_file(args.goal_file)
    if not goal:
        raise ValueError("Missing goal: provide --goal or --goal-file")
    return goal


def resolve_done_criteria(args: argparse.Namespace) -> str:
    done = (args.done_criteria or "").strip()
    if args.done_criteria_file:
        done = load_text_file(args.done_criteria_file)
    if not done:
        raise ValueError(
            "Missing done criteria: provide --done-criteria or --done-criteria-file"
        )
    return done


def _checks_from_file(path: str) -> list[str]:
    raw = Path(path).read_text(encoding="utf-8")
    out: list[str] = []
    for line in raw.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        out.append(item)
    return out


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def resolve_checks(args: argparse.Namespace) -> list[str]:
    checks: list[str] = list(args.check or [])
    for p in args.check_file or []:
        checks.extend(_checks_from_file(p))
    return dedupe_keep_order(checks)


def load_template(path: str | None, fallback: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return fallback


def load_schema(path: str | None, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path:
        return fallback
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"Schema at {path} must be a JSON object")
    return obj
