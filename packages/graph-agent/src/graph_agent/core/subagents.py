"""Subagent schema helpers for V2.1 engine-owned dispatcher metadata."""

from __future__ import annotations

from dataclasses import dataclass
from types import GenericAlias
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

MAX_SUBAGENT_SCHEMA_RETRIES = 10


@dataclass(frozen=True)
class SubagentValidationFailure:
    tool_name: str
    subagent_name: str
    retry_count: int
    message: str
    expected_schema: dict[str, Any]
    errors: list[dict[str, Any]]

    def to_tool_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error_type": "validation",
            "tool_name": self.tool_name,
            "subagent_name": self.subagent_name,
            "retry_count": self.retry_count,
            "message": self.message,
            "expected_schema": self.expected_schema,
            "errors": self.errors,
        }


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

    field_definitions = cast(dict[str, Any], fields)
    return create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        **field_definitions,
    )


def build_subagent_tool_args_model(
    model_name: str,
    input_model: type[BaseModel],
) -> type[BaseModel]:
    """Build the public `call_subagent_<name>` tool args model."""

    input_list_type: Any = GenericAlias(list, (input_model,))
    return create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        inputs=(
            input_list_type,
            Field(
                ...,
                description="Batch of subagent inputs. Best practice: pass no more than 3.",
            ),
        ),
    )


def validate_subagent_tool_args(
    *,
    tool_name: str,
    subagent_name: str,
    input_model: type[BaseModel],
    expected_schema: dict[str, Any],
    args: dict[str, Any],
    retry_count: int,
) -> list[BaseModel] | SubagentValidationFailure:
    if retry_count > MAX_SUBAGENT_SCHEMA_RETRIES:
        raise RuntimeError(
            f"call_subagent validation exceeded max retries: tool={tool_name} "
            f"retry_count={retry_count}"
        )
    inputs = args.get("inputs")
    if not isinstance(inputs, list):
        return SubagentValidationFailure(
            tool_name=tool_name,
            subagent_name=subagent_name,
            retry_count=retry_count,
            message=(
                "Validation Error: Expected {'inputs': list[object]} where each item matches "
                f"subagent {subagent_name!r} input schema. Please retry with correct schema."
            ),
            expected_schema=expected_schema,
            errors=[
                {
                    "loc": ["inputs"],
                    "msg": "Input should be a valid list",
                    "type": "list_type",
                }
            ],
        )
    validated: list[BaseModel] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(inputs):
        try:
            validated.append(input_model.model_validate(item))
        except ValidationError as exc:
            for error in exc.errors():
                error_copy = dict(error)
                error_copy["loc"] = ["inputs", index, *list(error.get("loc", ()))]
                errors.append(error_copy)
    if errors:
        return SubagentValidationFailure(
            tool_name=tool_name,
            subagent_name=subagent_name,
            retry_count=retry_count,
            message=(
                "Validation Error: subagent inputs did not match expected schema. "
                "Please retry with correct schema."
            ),
            expected_schema=expected_schema,
            errors=errors,
        )
    return validated


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


__all__ = [
    "MAX_SUBAGENT_SCHEMA_RETRIES",
    "SubagentValidationFailure",
    "build_subagent_input_model",
    "build_subagent_tool_args_model",
    "validate_subagent_tool_args",
]
