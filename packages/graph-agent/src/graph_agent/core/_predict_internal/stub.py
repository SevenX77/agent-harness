"""Heuristic stub generation entry point skeleton."""

from __future__ import annotations

from typing import Any

_UNKNOWN_VALUE = "<mock_unknown>"
_MAX_DEPTH = 20
_VALUE_NOT_HANDLED = object()


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

    schema_type = _schema_type_for_value(schema)

    if schema_type == "object":
        return _object_value_for_schema(schema, seen={*seen, schema_id}, depth=depth)

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return [
                _value_for_schema(
                    items,
                    field_name=field_name,
                    seen={*seen, schema_id},
                    depth=depth + 1,
                )
            ]
        return []

    primitive = _primitive_value_for_schema_type(schema_type, field_name=field_name)
    if primitive is not _VALUE_NOT_HANDLED:
        return primitive

    if field_name == "value":
        return _mock_string(None, unknown=True)
    return _mock_string(field_name, unknown=True)


def _schema_type_for_value(schema: dict[str, Any]) -> str | None:
    schema_type = _normalise_type(schema.get("type"))
    if schema_type is not None:
        return schema_type
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return None


def _object_value_for_schema(
    schema: dict[str, Any],
    *,
    seen: set[int],
    depth: int,
) -> dict[str, object]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}

    result: dict[str, object] = {}
    for name, child_schema in properties.items():
        if not isinstance(name, str):
            continue
        result[name] = _value_for_schema(
            child_schema,
            field_name=name,
            seen=seen,
            depth=depth + 1,
        )
    return result


def _primitive_value_for_schema_type(schema_type: str | None, *, field_name: str | None) -> object:
    if schema_type == "string":
        return _mock_string(field_name)
    if schema_type == "integer":
        integer_hint = _integer_value_for_field(field_name)
        if integer_hint is not _VALUE_NOT_HANDLED:
            return integer_hint
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return True
    return _VALUE_NOT_HANDLED


def _integer_value_for_field(field_name: str | None) -> object:
    if not field_name:
        return _VALUE_NOT_HANDLED
    normalized = field_name.lower()
    if normalized == "index" or normalized.endswith("_index"):
        return 1
    if normalized == "start_line" or normalized.endswith("_start_line"):
        return 1
    if normalized == "end_line" or normalized.endswith("_end_line"):
        return 999
    if normalized == "chapter_number" or normalized.endswith("_chapter_number"):
        return 1
    return _VALUE_NOT_HANDLED


def _is_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object" or isinstance(schema.get("properties"), dict)


def _normalise_type(raw_type: object) -> str | None:
    if isinstance(raw_type, str):
        return _normalise_type_string(raw_type)

    if isinstance(raw_type, list):
        for item in raw_type:
            parsed = _normalise_type(item)
            if parsed is not None and parsed != "null":
                return parsed
    return None


def _normalise_type_string(raw_type: str) -> str:
    lowered = raw_type.lower()
    aliases = {
        "dict": "object",
        "map": "object",
        "list": "array",
        "tuple": "array",
        "float": "number",
        "double": "number",
        "int": "integer",
        "bool": "boolean",
    }
    return aliases.get(lowered, lowered)


def _mock_string(field_name: str | None, *, unknown: bool = False) -> str:
    if unknown:
        return f"<mock_{field_name}>" if field_name else _UNKNOWN_VALUE
    return f"<mock_{field_name}>" if field_name else "<mock_data>"


__all__ = ["generate_heuristic_stub"]
