"""Built-in SKILL.md template endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.templates import SkillTemplate
from app.services.templates import list_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[SkillTemplate])
async def get_templates() -> list[SkillTemplate]:
    return list_templates()

