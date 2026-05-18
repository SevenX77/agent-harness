"""Subagent schema helpers for V2.1 engine-owned dispatcher metadata."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model


def build_subagent_input_model(model_name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Build a Pydantic input model from the supported V2.1 JSON Schema subset."""

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise ValueError("io.inputs schema must define a non-empty properties object")

    required_raw = schema.get("required", [])
    required = set(required_raw) if isinstance(required_raw, list) else set()
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, field_schema in properties.items():
        if not isinstance(field_name, str) or not isinstance(field_schema, dict):
            raise ValueError("io.inputs properties must map field names to schema objects")
        annotation = _annotation_for_json_schema(field_schema)
        default: Any
        if field_name in required:
            default = ...
        elif "default" in field_schema:
            default = field_schema["default"]
        else:
            default = None
        description = field_schema.get("description")
        fields[field_name] = (
            annotation,
            Field(default, description=description if isinstance(description, str) else None),
        )

    return create_model(  # type: ignore[call-overload]
        model_name,
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _annotation_for_json_schema(field_schema: dict[str, Any]) -> Any:
    schema_type = field_schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list[Any]
    if schema_type == "object":
        return dict[str, Any]
    return Any


__all__ = ["build_subagent_input_model"]
