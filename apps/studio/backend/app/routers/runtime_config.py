"""Runtime configuration API for Studio skills."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.runtime_config import RuntimeArtifactsRequest
from app.services.runtime_config import (
    refresh_runtime_config,
    remove_runtime_input_binding,
    restore_runtime_input_binding,
    update_artifacts_payload,
)
from app.services.skills import resolve_skill_dir

router = APIRouter(prefix="/api/skills/{skill_id}/runtime-config", tags=["runtime-config"])


class RuntimeInputIntentRequest(BaseModel):
    scope: str
    field: str


@router.get("")
def get_runtime_config(skill_id: str) -> dict[str, object]:
    return refresh_runtime_config(resolve_skill_dir(skill_id))


@router.put("/artifacts")
def put_runtime_artifacts(skill_id: str, request: RuntimeArtifactsRequest) -> dict[str, object]:
    skill_dir = resolve_skill_dir(skill_id)
    refresh_runtime_config(skill_dir)
    return update_artifacts_payload(
        skill_dir,
        [artifact.model_dump(mode="json") for artifact in request.artifacts],
    )


@router.post("/inputs/remove")
def remove_runtime_input(skill_id: str, request: RuntimeInputIntentRequest) -> dict[str, object]:
    return remove_runtime_input_binding(
        resolve_skill_dir(skill_id),
        scope=request.scope,
        field=request.field,
    )


@router.post("/inputs/restore")
def restore_runtime_input(skill_id: str, request: RuntimeInputIntentRequest) -> dict[str, object]:
    return restore_runtime_input_binding(
        resolve_skill_dir(skill_id),
        scope=request.scope,
        field=request.field,
    )
