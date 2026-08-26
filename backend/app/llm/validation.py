"""Structural validation for structured output.

Anthropic and Gemini enforce a JSON Schema server-side, so a response is
guaranteed to conform. Several OpenAI-compatible endpoints — Groq on older
models, Ollama — can only promise *valid JSON*, not JSON matching a shape.

Without a check, that difference surfaces far downstream as a `KeyError` inside
an agent, long after the run has spent tokens and the failing provider has been
forgotten. Validating at the boundary turns it into an ordinary provider
failure that the manager can fail over.

Only the constructs `llm/schema.py` emits are handled. A general-purpose
validator would be a dependency and a much larger surface for no gain: the
schemas being checked are all produced by that one module.
"""

from __future__ import annotations

from typing import Any

_TYPE_CHECKS: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate(data: Any, schema: dict[str, Any], *, path: str = "$") -> list[str]:
    """Return human-readable problems; an empty list means the data conforms."""
    problems: list[str] = []
    _validate_into(data, schema, path, problems)
    return problems


def normalize_unknown_fields(data: Any, schema: dict[str, Any]) -> Any:
    """Remove unknown keys from objects whose schema explicitly forbids them.

    Some OpenAI-compatible providers guarantee JSON but do not reliably honour
    ``additionalProperties: false``.  This is intentionally a narrow boundary
    transformation: known values are recursively preserved, required fields
    and their types are still checked by :func:`validate`, and objects that do
    not forbid additional properties are left unchanged.
    """
    expected = schema.get("type")

    if expected == "object" and isinstance(data, dict):
        properties = schema.get("properties", {})
        normalized: dict[str, Any] = {}
        for name, value in data.items():
            subschema = properties.get(name)
            if isinstance(subschema, dict):
                normalized[name] = normalize_unknown_fields(value, subschema)
            elif schema.get("additionalProperties") is not False:
                normalized[name] = value
        return normalized

    if expected == "array" and isinstance(data, list):
        items = schema.get("items")
        if isinstance(items, dict):
            return [normalize_unknown_fields(value, items) for value in data]

    return data


def _validate_into(data: Any, schema: dict[str, Any], path: str, out: list[str]) -> None:
    expected = schema.get("type")

    if expected in _TYPE_CHECKS:
        checker = _TYPE_CHECKS[expected]
        # bool is a subclass of int in Python; an integer field must not accept
        # True, or a capability flag silently becomes a count.
        if expected in ("integer", "number") and isinstance(data, bool):
            out.append(f"{path}: expected {expected}, got boolean")
            return
        if not isinstance(data, checker):
            out.append(f"{path}: expected {expected}, got {type(data).__name__}")
            return

    enum = schema.get("enum")
    if enum and data not in enum:
        out.append(f"{path}: {data!r} is not one of {enum}")

    if expected == "object" and isinstance(data, dict):
        properties: dict[str, Any] = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in data:
                out.append(f"{path}.{name}: required property is missing")
        if schema.get("additionalProperties") is False:
            for name in data:
                if name not in properties:
                    out.append(f"{path}.{name}: unexpected property")
        for name, value in data.items():
            subschema = properties.get(name)
            if isinstance(subschema, dict):
                _validate_into(value, subschema, f"{path}.{name}", out)

    if expected == "array" and isinstance(data, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(data):
                _validate_into(value, items, f"{path}[{index}]", out)


def describe_schema(schema: dict[str, Any]) -> str:
    """A prompt-ready description of the required shape.

    Providers that cannot take a schema parameter still follow one stated in
    the prompt reasonably well. This is the fallback path, paired with
    `validate` so that "reasonably well" is verified rather than assumed.
    """
    import json

    return (
        "Respond with a single JSON object and nothing else — no prose, no "
        "markdown fence. It must conform to this JSON Schema:\n"
        f"{json.dumps(schema, indent=2)}"
    )
