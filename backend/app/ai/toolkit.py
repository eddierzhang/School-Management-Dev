"""Tool definitions and argument validation.

A 4B model gets arguments wrong. Observed in testing: asked to inspect a course,
it called `list_items_for_course({"category": "All"})` — a parameter that tool
does not have, missing the one it requires. If that reaches a handler it raises a
TypeError and the run dies.

So every call is validated against the tool's schema first, and a failure is not
an exception — it is a `tool` message describing exactly what was wrong and what
the tool expects. The model then repairs the call. That repair loop is the single
highest-leverage piece of engineering for making small local models usable.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    proposes: str | None = None          # proposal kind, when this tool proposes rather than reads
    examples: list[str] = field(default_factory=list)

    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolError(Exception):
    """Recoverable: handed back to the model so it can fix the call."""


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    for name, types in JSON_TYPES.items():
        if name != "boolean" and isinstance(value, types):
            return name
    return type(value).__name__


def validate_arguments(tool: Tool, raw: Any) -> dict[str, Any]:
    """Return coerced arguments, or raise ToolError with a message the model can act on."""
    if not isinstance(raw, dict):
        raise ToolError(f"Arguments must be a JSON object. Got {_type_name(raw)}.")

    schema = tool.parameters
    props: dict[str, dict] = schema.get("properties", {}) or {}
    required: list[str] = schema.get("required", []) or []

    unknown = [k for k in raw if k not in props]
    missing = [k for k in required if k not in raw or raw[k] in (None, "")]
    if missing:
        raise ToolError(
            f"Missing required argument(s): {', '.join(missing)}. "
            f"{tool.name} takes: {_describe(props, required)}."
            + (f" You passed unknown argument(s): {', '.join(unknown)}." if unknown else "")
        )

    clean: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in props:
            continue                                  # ignore extras once the required set is satisfied
        spec = props[key]
        expected = spec.get("type", "string")
        allowed = JSON_TYPES.get(expected, (object,))

        if expected in ("integer", "number") and isinstance(value, str):
            try:                                      # small models quote their numbers
                value = float(value) if expected == "number" else int(float(value))
            except ValueError:
                raise ToolError(f"Argument '{key}' must be {expected}. Got the string {value!r}.") from None
        if expected == "integer" and isinstance(value, float) and value.is_integer():
            value = int(value)
        if expected == "array" and isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]

        if not isinstance(value, allowed) or (expected != "boolean" and isinstance(value, bool)):
            raise ToolError(f"Argument '{key}' must be {expected}. Got {_type_name(value)}.")

        enum = spec.get("enum")
        if enum and value not in enum:
            raise ToolError(f"Argument '{key}' must be one of: {', '.join(map(str, enum))}. Got {value!r}.")

        if expected == "array":
            item_type = (spec.get("items") or {}).get("type", "string")
            allowed_item = JSON_TYPES.get(item_type, (object,))
            for v in value:
                if not isinstance(v, allowed_item):
                    raise ToolError(f"Every item in '{key}' must be {item_type}. Got {_type_name(v)}.")

        clean[key] = value

    for key in required:
        if key not in clean:
            raise ToolError(f"Missing required argument '{key}'. {tool.name} takes: {_describe(props, required)}.")
    return clean


def _describe(props: dict[str, dict], required: list[str]) -> str:
    parts = []
    for name, spec in props.items():
        flag = "required" if name in required else "optional"
        parts.append(f"{name} ({spec.get('type', 'string')}, {flag})")
    return "; ".join(parts) or "no arguments"


def call(tool: Tool, raw_args: Any, db: Session, ctx: dict) -> Any:
    """Validate then invoke. ToolError propagates to the runner as a repairable message."""
    args = validate_arguments(tool, raw_args)
    return tool.handler(db=db, ctx=ctx, **args)
