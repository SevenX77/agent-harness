"""Run request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from graph_agent import PathDiff, PhaseRecord
from graph_agent.core.event_contracts import EventEnvelope
from pydantic import BaseModel, ConfigDict, Field


class TokensMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float | None = None
    # ⑧a: engine run wall-clock duration. Declared explicitly (keeping extra="forbid"
    # for a controllable surface) so the engine's wall_time_sec survives the Studio
    # projection and reaches the frontend run history instead of being stripped.
    wall_time_sec: float | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_data: dict[str, Any] | None = None
    golden_id: str | None = None
    paste_json: str | None = None


class PredictRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_data: dict[str, Any] | None = None
    mock_llm: Any = None
    current_hashes: dict[str, dict[str, str]] | None = None


class PredictDiagnosticExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_predict: bool
    status: Literal["success", "failed"]
    phases: list[PhaseRecord]
    path_diff: PathDiff | None = None


class BatchRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ids: list[str]


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["running", "success", "failed"]
    started_at: datetime
    metrics: TokensMetrics | None = None
    input_summary: str | None = None
    git_status: Literal["committed", "locked", "failed", "no_git"] | None = None
    artifact_ref: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)
    source_map_ref: str | None = Field(default=None, exclude_if=lambda value: value is None)
    execution_fingerprint: str | None = Field(default=None, exclude_if=lambda value: value is None)


class RunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[RunMetadata]
    total: int


class BatchRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    sub_run_ids: list[str]


class BatchRunItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    run_id: str
    status: Literal["running", "success", "failed"]
    started_at: datetime
    metrics: TokensMetrics | None = None


class BatchRunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    skill_id: str
    status: Literal["running", "success", "failed"]
    total: int
    completed: int
    items: list[BatchRunItem]


class RunDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: RunMetadata
    input_data: dict[str, Any] | None = None
    events: list[EventEnvelope]
    final_context: dict[str, Any] | None = None
    artifacts: list[str] | None = None


class ResumeReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None
    resume_from_node_id: str | None = None
    resume_to_node_id: str | None = None
    context_overrides: dict[str, Any] | None = None
    human_input: str | None = None
    human_response: dict[str, Any] | None = None


class ResumeValidityReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None
    resume_from_node_id: str | None = None
    resume_to_node_id: str | None = None


class ResumeValidityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    resume_allowed: bool
    reason: Literal[
        "ok",
        "dirty_upstream",
        "checkpoint.not_found",
        "checkpoint.invalid",
        "state.not_found",
        "artifact.invalid_ref",
        "artifact.identity_mismatch",
        "compile_failed",
    ]
    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None
    resume_from_node_id: str | None = None
    resume_to_node_id: str | None = None
    dirty_fields: list[Literal["content_hash", "execution_fingerprint"]] = Field(default_factory=list)
    snapshot_content_hash: str | None = None
    current_content_hash: str | None = None
    snapshot_execution_fingerprint: str | None = None
    current_execution_fingerprint: str | None = None
