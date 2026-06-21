"""Lint endpoint.

Realtime lint (compile-lint F1) sends the editor's *unsaved* changed-markdown so
the engine can check what the user is typing, not just what is on disk. The lint
kernel stays engine-owned; this router only forwards the body. When no body is
supplied the endpoint falls back to linting the on-disk skill (backward-compat).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.models.lint import LintResult
from app.services.skills import lint_skill as lint_skill_service
from app.services.skills import lint_skill_changed_markdown

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["lint"])


class LintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str | None = None


@router.post("/lint", response_model=LintResult)
async def lint_skill(skill_id: str, body: LintRequest | None = None) -> LintResult:
    if body is not None and body.markdown is not None:
        return lint_skill_changed_markdown(skill_id, body.markdown)
    return lint_skill_service(skill_id)
