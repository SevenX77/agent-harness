from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from graph_agent.core.artifacts import ArtifactRef


class RunArtifactRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: ArtifactRef
    inputs: dict[str, Any] = Field(default_factory=dict)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class PredictArtifactRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: ArtifactRef
    inputs: dict[str, Any] = Field(default_factory=dict)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class ResumeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class RunSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    event_stream_ref: str
    result_ref: str | None = None
    status_ref: str | None = None


class RunArtifactErrorResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    error_code: str
    error_payload: dict[str, Any]
    run_id: str | None = None
    retryable: bool = False

