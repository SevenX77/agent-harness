"""Runtime configuration API for Studio skills."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.runtime_config import (
    refresh_runtime_config,
    update_artifacts_payload,
)
from app.services.skills import resolve_skill_dir

router = APIRouter(prefix="/api/skills/{skill_id}/runtime-config", tags=["runtime-config"])


class RuntimeArtifact(BaseModel):
    stem: str
    mode: Literal["single", "per-item"] = "single"
    format: Literal["json", "md"] = "json"
    fields: list[str] = Field(default_factory=list)


class RuntimeArtifactsRequest(BaseModel):
    artifacts: list[RuntimeArtifact] = Field(default_factory=list)


@router.get("")
def get_runtime_config(skill_id: str) -> dict[str, object]:
    return refresh_runtime_config(resolve_skill_dir(skill_id))


@router.put("/artifacts")
def put_runtime_artifacts(skill_id: str, request: RuntimeArtifactsRequest) -> dict[str, object]:
    skill_dir = resolve_skill_dir(skill_id)
    refresh_runtime_config(skill_dir)
    artifacts = [
        {
            "stem": artifact.stem,
            "mode": artifact.mode,
            "format": artifact.format,
            "fields": artifact.fields,
        }
        for artifact in request.artifacts
    ]
    return update_artifacts_payload(skill_dir, artifacts)
