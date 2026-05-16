"""File-backed skill input validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.encoders import jsonable_encoder
from graph_agent import compile_skill
from graph_agent.core.loader import SkillLoader
from graph_agent.core.exceptions import SkillCompilationError, SkillLoadError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    create_model,
)

from app.core.ports.storage import StorageBackend
from app.services.skills import resolve_skill_dir_async

_TYPE_MAP: dict[str, Any] = {
    "str": StrictStr,
    "string": StrictStr,
    "int": StrictInt,
    "integer": StrictInt,
    "float": StrictFloat,
    "bool": StrictBool,
    "boolean": StrictBool,
    "dict": dict[str, Any],
    "object": dict[str, Any],
    "list": list[Any],
    "array": list[Any],
}
_JSON_TYPE_MAP: dict[str, Any] = {
    "string": StrictStr,
    "integer": StrictInt,
    "number": StrictFloat,
    "boolean": StrictBool,
    "object": dict[str, Any],
    "array": list[Any],
}
_YAML: Any = import_module("yaml")


@dataclass(frozen=True)
class ValidationHttpError(Exception):
    status_code: int
    body: dict[str, Any]


async def validate_skill_input_file(
    user_id: str,
    skill_id: str,
    input_file_path: str,
    storage: StorageBackend,
) -> dict[str, Any]:
    """Validate a JSON/YAML file against a skill's declared runtime inputs."""
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage)
    input_schema = _compile_input_schema_or_raise(skill_dir)
    parsed_data = _parse_input_file(Path(input_file_path))
    input_model = _input_model_for_schema(input_schema)

    try:
        validated = input_model.model_validate(parsed_data)
    except ValidationError as exc:
        raise ValidationHttpError(
            status_code=422,
            body={"errors": jsonable_encoder(exc.errors())},
        ) from exc
    return validated.model_dump()


def _compile_input_schema_or_raise(skill_path: Path) -> dict[str, Any]:
    try:
        compile_skill(skill_path)
        compiled = SkillLoader().compile_skill(skill_path)
    except (SkillLoadError, SkillCompilationError):
        raise ValidationHttpError(
            status_code=422,
            body={"detail": "skill itself failed to compile, fix it first"},
        )
    input_schema = compiled.raw.get("io", {}).get("inputs")
    if not isinstance(input_schema, dict):
        raise ValidationHttpError(
            status_code=422,
            body={"detail": "skill does not declare graph runtime inputs"},
        )
    return input_schema


def _parse_input_file(path: Path) -> Any:
    if not path.exists():
        raise ValidationHttpError(status_code=404, body={"detail": "input file not found"})

    suffix = path.suffix.lower()
    try:
        content = path.read_text(encoding="utf-8")
        if suffix == ".json":
            return json.loads(content)
        if suffix in {".yaml", ".yml"}:
            return _YAML.safe_load(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _YAML.YAMLError) as exc:
        raise _parse_error(exc) from exc

    raise _parse_error(ValueError(f"unsupported input file extension: {suffix or '<none>'}"))


def _parse_error(exc: Exception) -> ValidationHttpError:
    return ValidationHttpError(
        status_code=422,
        body={
            "errors": [
                {
                    "loc": ["__file__"],
                    "msg": f"JSON/YAML parse error: {exc}",
                    "type": "value_error.parse",
                },
            ],
        },
    )


def _input_model_for_schema(input_schema: dict[str, Any]) -> type[BaseModel]:
    fields: dict[str, tuple[Any, Any]] = {}
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    if not isinstance(properties, dict):
        properties = {}
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            schema = {}
        default = Field(...) if name in required else schema.get("default", None)
        fields[str(name)] = (_python_type_from_schema(schema), default)
    field_definitions = cast(Mapping[str, Any], fields)
    return cast(
        type[BaseModel],
        create_model(
            "SkillInputModel",
            __config__=ConfigDict(extra="forbid"),
            **field_definitions,
        ),
    )


def _python_type_from_schema(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), None)
    if schema_type is None:
        return Any
    return _JSON_TYPE_MAP.get(str(schema_type).strip().lower(), Any)
