"""Lint endpoint.

Realtime lint (compile-lint F1) has two trigger shapes:
- editor typing sends the *unsaved* changed-markdown body so the engine checks
  what the user is typing, not just what is on disk;
- a canvas topology write (03_compile A13) sends NO markdown — the write already
  settled, so the on-disk tree is the source truth (``workspace_root`` locates
  workspace-based skills).
The lint kernel stays engine-owned; this router only routes the request shape.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.models.lint import LintResult
from app.services.skills import lint_skill_changed_markdown, lint_skill_on_disk

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["lint"])


class LintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str | None = None
    file_path: str | None = None
    workspace_root: str | None = None


@router.post("/lint", response_model=LintResult)
async def lint_skill(skill_id: str, body: LintRequest | None = None) -> LintResult:
    if body is not None and body.markdown is not None:
        return lint_skill_changed_markdown(
            skill_id,
            body.markdown,
            file_path=body.file_path,
            workspace_root=body.workspace_root,
        )
    return lint_skill_on_disk(skill_id, body.workspace_root if body is not None else None)
