"""Skill lifecycle endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.backends import get_auth_user_id, get_metadata, get_storage
from app.core.exceptions import raise_not_implemented
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.errors import ErrorResponse
from app.models.skills import (
    CreateSkillReq,
    ForkSkillReq,
    SkillDetail,
    SkillSummary,
    UpdateSkillReq,
)
from app.services.skills import (
    create_new_skill,
    fork_skill,
    get_skill_detail,
    list_skill_summaries,
    update_skill_content,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummary])
async def list_skills(
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> list[SkillSummary]:
    return await list_skill_summaries(user_id, storage, metadata)


@router.post("", response_model=SkillSummary, status_code=201)
async def create_skill(
    request: CreateSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillSummary:
    return await create_new_skill(user_id, request.skill_id, request.content, storage, metadata)


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillDetail:
    return await get_skill_detail(user_id, skill_id, storage, metadata)


@router.put("/{skill_id}", response_model=SkillDetail)
async def update_skill(
    skill_id: str,
    request: UpdateSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillDetail:
    return await update_skill_content(user_id, skill_id, request.content, storage, metadata)


@router.post("/{skill_id}/fork", response_model=SkillSummary, status_code=201)
async def fork_existing_skill(
    skill_id: str,
    request: ForkSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillSummary:
    return await fork_skill(user_id, skill_id, request.new_skill_id, storage, metadata)


@router.delete(
    "/{skill_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_skill(skill_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete skill {skill_id}")
