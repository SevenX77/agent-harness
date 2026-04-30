"""Skill lifecycle endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.skills import CreateSkillReq, SkillDetail, SkillSummary, UpdateSkillReq
from app.services.placeholders import placeholder_skill_detail, placeholder_skill_summary

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummary])
async def list_skills() -> list[SkillSummary]:
    return [placeholder_skill_summary()]


@router.post("", response_model=SkillSummary, status_code=201)
async def create_skill(request: CreateSkillReq) -> SkillSummary:
    skill_id = request.template_id or "new-skill"
    description = request.description or "Phase 0 Studio placeholder skill"
    return placeholder_skill_summary(skill_id=skill_id, description=description)


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(skill_id: str) -> SkillDetail:
    return placeholder_skill_detail(skill_id)


@router.put("/{skill_id}", response_model=SkillDetail)
async def update_skill(skill_id: str, request: UpdateSkillReq) -> SkillDetail:
    if not request.content:
        raise ValueError("Skill content must not be empty")
    return placeholder_skill_detail(skill_id)


@router.delete(
    "/{skill_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_skill(skill_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete skill {skill_id}")
