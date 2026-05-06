"""Skill listing and detail models."""

from __future__ import annotations

from datetime import datetime

from graph_agent.core.manifest import SkillManifest
from pydantic import BaseModel, ConfigDict, Field

from app.models.lint import LintResult
from app.models.runs import RunMetadata


class SkillSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    phase_count: int
    has_golden: bool
    last_run_at: datetime | None = None


class SkillDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: SkillManifest
    file_paths: dict[str, str]
    has_golden: bool
    latest_run_metadata: RunMetadata | None = None
    lint_result: LintResult | None = None


class CreateSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(..., pattern=r"^[a-z][a-z0-9-]+$")
    content: str


class ForkSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_skill_id: str = Field(..., pattern=r"^[a-z][a-z0-9-]+$")


class UpdateSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
