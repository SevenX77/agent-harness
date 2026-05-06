"""Copilot dispatch endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.copilot import CopilotDispatchReq, CopilotResponse
from app.models.errors import ErrorResponse

router = APIRouter(prefix="/api/skills/{skill_id}/copilot", tags=["copilot"])


@router.post(
    "/dispatch",
    response_model=CopilotResponse,
    responses={501: {"model": ErrorResponse}},
)
async def dispatch_copilot(skill_id: str, request: CopilotDispatchReq) -> CopilotResponse:
    raise_not_implemented(f"dispatch copilot for skill {skill_id}")
