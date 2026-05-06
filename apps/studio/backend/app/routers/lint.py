"""Lint endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.lint import LintResult
from app.services.skills import lint_skill as lint_skill_service

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["lint"])


@router.post("/lint", response_model=LintResult)
async def lint_skill(skill_id: str) -> LintResult:
    return lint_skill_service(skill_id)
