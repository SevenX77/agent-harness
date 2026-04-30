"""Skill lifecycle endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.skills import CreateSkillReq, SkillDetail, SkillSummary, UpdateSkillReq
from app.services.skills import get_skill_detail, list_skill_summaries, update_skill_content

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummary])
async def list_skills() -> list[SkillSummary]:
    return list_skill_summaries()


@router.post("", response_model=SkillSummary, status_code=201)
async def create_skill(request: CreateSkillReq) -> SkillSummary:
    raise_not_implemented(f"create skill from template {request.template_id or 'blank'}")


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(skill_id: str) -> SkillDetail:
    return get_skill_detail(skill_id)


@router.put("/{skill_id}", response_model=SkillDetail)
async def update_skill(skill_id: str, request: UpdateSkillReq) -> SkillDetail:
    return update_skill_content(skill_id, request.content)


@router.delete(
    "/{skill_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_skill(skill_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete skill {skill_id}")
