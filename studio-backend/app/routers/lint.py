"""Lint endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.lint import LintResult

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["lint"])


@router.post("/lint", response_model=LintResult)
async def lint_skill(skill_id: str) -> LintResult:
    return LintResult(
        status="passed",
        errors=[],
        phases_summary=[{"name": skill_id, "tier": "phase0", "has_validator": False}],
    )
