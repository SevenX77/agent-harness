"""Golden baseline models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoldenBaselineCase(BaseModel):
    """One agent node's golden case, projected from baseline.json for the UI badge."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    node_id: str
    phase_id: str
    expected_output_ref: str


class GoldenBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_run_id: str | None = None
    source_run_results_ref: str | None = None
    baseline_ref: str | None = None
    linked_input_id: str
    created_at: datetime
    locked: bool
    content_path: str
    cases: list[GoldenBaselineCase] = Field(default_factory=list)


class GoldenBaselineFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class GoldenBaselinePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: GoldenBaseline
    files: list[GoldenBaselineFile]


class SetGoldenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    lock: bool
    node_id: str | None = None


class CopilotJudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_results_ref: str | None = None
    baseline_ref: str | None = None
    against: str | None = None


class CopilotJudgeDiffSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_id: str
    run_results_ref: str
    total_score: float
    node_group_count: int
    failed_node_count: int


class CopilotJudgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compare_result_ref: str
    judge_context_ref: str
    baseline_ref: str
    diff_summary: CopilotJudgeDiffSummary
