"""Skill listing and detail models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from graph_agent.core.manifest import SkillManifest
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.errors import LintError
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
    directory_path: str | None = None


class SkillDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: SkillManifest
    graph_topology: list[dict[str, object]] = Field(default_factory=list)
    node_schema_v21: dict[str, dict[str, object]] = Field(default_factory=dict)
    io_schema: dict[str, dict[str, object]] = Field(default_factory=dict)
    file_paths: dict[str, str]
    files: dict[str, str] = Field(default_factory=dict)
    has_golden: bool
    latest_run_metadata: RunMetadata | None = None
    lint_result: LintResult | None = None
    manifest_errors: list[LintError] | None = None


class PhaseRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_mode(cls, value: Any) -> Any:
        if isinstance(value, dict) and "mode" in value:
            normalized = dict(value)
            normalized.pop("mode", None)
            return normalized
        return value

    id: str = Field(..., min_length=1)
    src: str = Field(..., min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    output: bool = False


class ChildGraphTopology(BaseModel):
    """Child graph resolved by absolute path for inline subgraph rendering."""

    model_config = ConfigDict(extra="forbid")

    path: str
    name: str
    description: str = ""
    phases: list[str] = Field(default_factory=list)
    graph_topology: list[dict[str, object]] = Field(default_factory=list)
    detail: SkillDetail | None = None


class SerializeGraphReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phases: list[PhaseRef]
    expected_hash: str | None = None

    @model_validator(mode="after")
    def reject_duplicate_phase_ids(self) -> SerializeGraphReq:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for phase in self.phases:
            if phase.id in seen:
                duplicates.add(phase.id)
            seen.add(phase.id)
        if duplicates:
            raise ValueError(f"duplicate phase id(s): {', '.join(sorted(duplicates))}")
        return self


class SerializeGraphRes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown_content: str
    phase_count: int
    elapsed_ms: float
    current_hash: str


class CompileError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str | None = None
    line: int | None = None
    field: str | None = None
    severity: Literal["fatal", "warning"] = "fatal"
    message: str
    error_code: str | None = None


class CompileSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    status: Literal["ok"]
    phase_count: int
    manifest_name: str
    artifact_ref: dict[str, Any]
    source_map_ref: str
    execution_fingerprint: str


class CompileFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["compile_failed"] = "compile_failed"
    detail: str
    errors: list[CompileError]


class CreateSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(..., pattern=r"^[a-z][a-z0-9-]+$")
    files: dict[str, str] = Field(default_factory=dict)
    directory_path: str | None = None
    import_existing: bool = False


class ForkSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_skill_id: str = Field(..., pattern=r"^[a-z][a-z0-9-]+$")


class UpdateSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: dict[str, str]
    expected_hash: str | None = None


class UpdateSkillFileReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    expected_hash: str | None = None


class UpdateSkillFileRes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    hash: str
