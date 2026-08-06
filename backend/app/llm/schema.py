"""Helpers for building strict JSON Schemas for structured model output.

The Claude structured-outputs feature requires every object to declare
`additionalProperties: false` and list its `required` keys. These builders make
that invariant impossible to forget.
"""

from __future__ import annotations

from typing import Any


def obj(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """A strict object schema. All properties are required unless narrowed."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def array(items: dict[str, Any], *, description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if description:
        schema["description"] = description
    return schema


def string(description: str, *, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        schema["enum"] = enum
    return schema


def integer(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def number(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def boolean(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def string_array(description: str) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": {"type": "string"}}


# --- Reusable composite schemas -----------------------------------------

FILE_SCHEMA = obj(
    {
        "path": string(
            "Repository-relative POSIX path, e.g. 'src/components/Button.tsx'. "
            "No leading slash, no '..' segments."
        ),
        "content": string("Complete file contents. Never truncated, never elided."),
        "description": string("One line describing the file's responsibility."),
    }
)

FILE_BUNDLE_SCHEMA = obj(
    {
        "files": array(FILE_SCHEMA, description="Every file produced in this batch."),
        "notes": string("Implementation notes for downstream agents. May be empty."),
    }
)

FILE_PLAN_ENTRY_SCHEMA = obj(
    {
        "path": string("Repository-relative POSIX path for the planned file."),
        "purpose": string("What this file is responsible for."),
        "depends_on": string_array("Paths this file imports from. May be empty."),
        "priority": integer("Generation order, 1 = generate first."),
    }
)

FILE_PLAN_SCHEMA = obj(
    {
        "files": array(FILE_PLAN_ENTRY_SCHEMA, description="The complete file manifest."),
        "rationale": string("Why this structure was chosen."),
    }
)
