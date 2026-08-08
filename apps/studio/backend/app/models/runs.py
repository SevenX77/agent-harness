"""Run request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from graph_agent import PathDiff, PhaseRecord
from graph_agent.core.event_contracts import EventEnvelope
from graph_agent.core.exceptions import ErrorPayload
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


class NodeCompareRunRequest(BaseModel):
    """PR2 node-level Compare LLMs trigger.

    Launches, off a completed base run, one isolated single-node side-run per
    persisted candidate of ``node_id`` (candidates read from the skill's
    compare-candidates store). Each side-run feeds the node the exact input the
    base run gave it, swapping only the model — never touches the base run.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1)


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
    error: ErrorPayload | None = None
    diagnostics: list[ErrorPayload] = Field(default_factory=list)
    diagnostics_truncated: bool = False
    diagnostic_counts: dict[str, Any] = Field(default_factory=dict)


class BatchRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ids: list[str]


#: What a run can be.
#:
#: ``paused`` and ``cancelled`` are different things and the engine is why: a run
#: only cleans up its checkpoints when it finishes on its own, so a worker stopped
#: mid-flight leaves a checkpoint that ``resume_skill`` can pick up. Pausing is
#: therefore not an ending — the run is waiting to be continued. ``cancelled`` is
#: the ending the user chose, and neither is a failure.
#:
#: Declared once because a run's status travels through the batch views too, and a
#: vocabulary that is only half-extended rejects its own data at validation.
RunStatus = Literal["running", "success", "failed", "paused", "cancelled"]


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    started_at: datetime
    # Timeline F1: predict attempts sit in the same run list as real runs and
    # are told apart by this field alone (PM: predict 行仅用 icon 区分).
    kind: Literal["run", "predict"] = "run"
    metrics: TokensMetrics | None = None
    input_summary: str | None = None
    git_status: Literal["committed", "unchanged", "locked", "failed", "no_git"] | None = None
    artifact_ref: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)
    source_map_ref: str | None = Field(default=None, exclude_if=lambda value: value is None)
    execution_fingerprint: str | None = Field(default=None, exclude_if=lambda value: value is None)
    # PR2 node-compare grouping. Set only on candidate side-runs so the frontend
    # can group/tab per-candidate results under the compared node; omitted on
    # ordinary runs. ``candidate_label`` is the human tab label (model group).
    compare_group_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    compare_node_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    candidate_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    candidate_label: str | None = Field(default=None, exclude_if=lambda value: value is None)


class RunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[RunMetadata]
    total: int


class CompareCandidateRun(BaseModel):
    """One candidate's isolated single-node side-run within a compare group."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    label: str
    metadata: RunMetadata


class CompareRunResponse(BaseModel):
    """POST response: the compare group + the per-candidate side-runs it spawned."""

    model_config = ConfigDict(extra="forbid")

    compare_group_id: str
    node_id: str
    base_run_id: str
    runs: list[CompareCandidateRun]


class CompareRunGroupResponse(BaseModel):
    """GET response: per-candidate side-runs for one compare group, for Trace tabs."""

    model_config = ConfigDict(extra="forbid")

    compare_group_id: str
    runs: list[CompareCandidateRun]


class BatchRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    sub_run_ids: list[str]


class BatchRunItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    run_id: str
    status: RunStatus
    started_at: datetime
    metrics: TokensMetrics | None = None


class BatchRunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    skill_id: str
    status: RunStatus
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
    # n5-node#3 (dirty-downstream-graying): per-node dirty slice. When the
    # whole-skill compare is dirty and resume_from_node_id is set, the Studio
    # shell projects which downstream phases the resume node can dirty so the
    # frontend grays exactly those. Dependency-graph based (the engine has no
    # per-node hash) -- empty on the clean / no-resume-node paths.
    dirty_node_ids: list[str] = Field(default_factory=list)
    affected_downstream: list[str] = Field(default_factory=list)
    snapshot_content_hash: str | None = None
    current_content_hash: str | None = None
    snapshot_execution_fingerprint: str | None = None
    current_execution_fingerprint: str | None = None
