"""Intent drift audit endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.audit import AuditResult
from app.models.errors import ErrorResponse

router = APIRouter(prefix="/api/skills/{skill_id}/runs/{run_id}", tags=["audit"])


@router.get(
    "/audit",
    response_model=AuditResult,
    responses={501: {"model": ErrorResponse}},
)
async def get_run_audit(skill_id: str, run_id: str) -> AuditResult:
    raise_not_implemented(f"audit run {run_id} for skill {skill_id}")
