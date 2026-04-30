"""Skill lint response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.errors import LintError


class LintResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "failed"]
    errors: list[LintError]
    phases_summary: list[dict[str, Any]] | None = None
