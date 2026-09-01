"""Skill input validation: does this payload satisfy the skill's declared inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fastapi.encoders import jsonable_encoder
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

from app.core.adapters.engine import GraphAgentError, GraphManifest, SkillLoader
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.services.skill_resolver import build_studio_skill_resolver
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


@dataclass(frozen=True)
class ValidationHttpError(Exception):
    status_code: int
    body: dict[str, Any]


async def validate_skill_input(
    user_id: str,
    skill_id: str,
    input_data: dict[str, Any],
    storage: StorageBackend,
    metadata: MetadataStore,
) -> dict[str, Any]:
    """Validate a submitted input payload against a skill's declared runtime inputs."""
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    manifest, raw_io = _compile_manifest_or_raise(skill_dir)
    input_model = _input_model_for_manifest(manifest, raw_io)

    try:
        validated = input_model.model_validate(input_data)
    except ValidationError as exc:
        raise ValidationHttpError(
            status_code=422,
            body={"errors": jsonable_encoder(exc.errors())},
        ) from exc
    return validated.model_dump()


def _compile_manifest_or_raise(skill_path: Path) -> tuple[GraphManifest, dict[str, Any]]:
    try:
        compiled = SkillLoader().compile_skill(
            skill_path,
            skill_resolver=build_studio_skill_resolver(),
        )
    except GraphAgentError as exc:
        del exc
        raise ValidationHttpError(
            status_code=422,
            body={"detail": "skill itself failed to compile, fix it first"},
        ) from None
    return compiled.manifest, dict(compiled.raw["io"]["inputs"])


def _input_model_for_manifest(
    manifest: GraphManifest,
    raw_inputs: dict[str, Any],
) -> type[BaseModel]:
    del manifest
    fields: dict[str, tuple[Any, Any]] = {}
    properties = raw_inputs.get("properties", {})
    required = set(raw_inputs.get("required", []))
    if not isinstance(properties, dict):
        properties = {}
    for name, input_decl in properties.items():
        if isinstance(input_decl, dict):
            default = input_decl.get("default", Field(... if name in required else None))
            fields[name] = (_python_type_from_input(input_decl), default)
        else:
            fields[name] = (Any, Field(...))
    field_definitions = cast(Mapping[str, Any], fields)
    return cast(
        type[BaseModel],
        create_model(
            "SkillInputModel",
            __config__=ConfigDict(extra="forbid"),
            **field_definitions,
        ),
    )


def _python_type_from_input(input_decl: dict[str, Any]) -> Any:
    input_type = input_decl.get("type")
    if not isinstance(input_type, str):
        return Any
    return _TYPE_MAP.get(input_type.strip().lower(), Any)
