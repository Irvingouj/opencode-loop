from __future__ import annotations

import json
from typing import Any


def render_template(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def compose(prefix: str, body: str) -> str:
    if prefix:
        return f"{prefix}\n\n{body}"
    return body


def list_to_bullets(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {x}" for x in items)


def schema_text(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2)


def _pick_first_str(d: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _compact_json(obj: dict[str, Any], limit: int = 280) -> str:
    compact = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if len(compact) > limit:
        return compact[:limit] + "...(truncated)"
    return compact
