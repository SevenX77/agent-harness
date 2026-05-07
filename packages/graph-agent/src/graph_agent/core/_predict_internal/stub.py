"""Heuristic stub generation entry point skeleton."""

from __future__ import annotations

from typing import Any

_UNKNOWN_VALUE = "<mock_unknown>"
_MAX_DEPTH = 20


def generate_heuristic_stub(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Generate a structure-valid, visibly fake payload for a JSON schema.

    Predict uses this as a P2 fallback to keep downstream LogicPhase code
    moving.  The values are intentionally deterministic and non-semantic.
    """
    if not isinstance(schema, dict):
        return {"value": _UNKNOWN_VALUE}
    if not schema:
        return {"value": _UNKNOWN_VALUE}

    if _is_object_schema(schema):
        value = _value_for_schema(schema, field_name=None, seen=set(), depth=0)
        return value if isinstance(value, dict) else {"value": value}

    return {"value": _value_for_schema(schema, field_name="value", seen=set(), depth=0)}


def _value_for_schema(
    schema: object,
    *,
    field_name: str | None,
    seen: set[int],
    depth: int,
) -> object:
    if not isinstance(schema, dict):
        return _mock_string(field_name, unknown=True)

    schema_id = id(schema)
    if schema_id in seen or depth >= _MAX_DEPTH:
        return _mock_string(field_name, unknown=field_name is None)

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    raw_type = schema.get("type")
    schema_type = _normalise_type(raw_type)
    if schema_type is None:
        if "properties" in schema:
            schema_type = "object"
        elif "items" in schema:
            schema_type = "array"

    if schema_type == "object":
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return {}

        next_seen = {*seen, schema_id}
        result: dict[str, object] = {}
        for name, child_schema in properties.items():
            if not isinstance(name, str):
                continue
            result[name] = _value_for_schema(
                child_schema,
                field_name=name,
                seen=next_seen,
                depth=depth + 1,
            )
        return result

    if schema_type == "array":
        return []

    if schema_type == "string":
        return _mock_string(field_name)

    if schema_type == "integer":
        return 0

    if schema_type == "number":
        return 0.0

    if schema_type == "boolean":
        return True

    if field_name == "value":
        return _mock_string(None, unknown=True)
    return _mock_string(field_name, unknown=True)


def _is_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object" or isinstance(schema.get("properties"), dict)


def _normalise_type(raw_type: object) -> str | None:
    if isinstance(raw_type, str):
        lowered = raw_type.lower()
        if lowered in {"object", "array", "string", "integer", "number", "boolean"}:
            return lowered
        if lowered in {"dict", "map"}:
            return "object"
        if lowered in {"list", "tuple"}:
            return "array"
        if lowered in {"float", "double"}:
            return "number"
        if lowered in {"int"}:
            return "integer"
        if lowered in {"bool"}:
            return "boolean"
        return lowered

    if isinstance(raw_type, list):
        for item in raw_type:
            parsed = _normalise_type(item)
            if parsed is not None and parsed != "null":
                return parsed
    return None


def _mock_string(field_name: str | None, *, unknown: bool = False) -> str:
    if unknown:
        return f"<mock_{field_name}>" if field_name else _UNKNOWN_VALUE
    return f"<mock_{field_name}>" if field_name else "<mock_data>"


__all__ = ["generate_heuristic_stub"]
