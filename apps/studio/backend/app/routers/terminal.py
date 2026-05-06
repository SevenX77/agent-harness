"""Terminal endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.terminal import TerminalSession
from app.services.terminal_manager import terminal_manager

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["terminal"])


@router.post("/terminal", response_model=TerminalSession, status_code=201)
async def create_terminal_session(skill_id: str) -> TerminalSession:
    return terminal_manager.create_terminal(skill_id)
