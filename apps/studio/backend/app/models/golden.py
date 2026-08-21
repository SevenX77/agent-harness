"""Golden baseline models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class GoldenCaseContent(BaseModel):
    """One agent node's stored golden case content (the editable expected_output).

    N4 atom #29 read path: the list endpoint only projects per-node case metadata
    (``case_id``/``node_id``/``expected_output_ref``); this model carries the actual
    ``expected_output`` the ref points at, so the I/O panel can open a golden file for
    editing. Read-only — this model carries no write path.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    node_id: str
    phase_id: str
    expected_output: dict[str, Any]


class GoldenBaselineContent(BaseModel):
    """A golden baseline with each case's resolved expected_output content.

    N4 atom #29: returned by ``GET /golden/{golden_id}/content`` so the frontend can open
    an existing baseline (or a single node's case via ``?node_id=``) for editing.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    source_run_id: str | None = None
    locked: bool
    cases: list[GoldenCaseContent] = Field(default_factory=list)


class GoldenBaselinePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: GoldenBaseline
    files: list[GoldenBaselineFile]


GoldenSeedReason = Literal["absent", "case_file_missing", "expected_output_invalid"]
"""Why a node had no usable golden — the three shapes F6 seeds from a Run's output.

They are one verdict with three causes, kept apart only so the UI can say what it
filled. ``absent`` = the baseline never listed this node; ``case_file_missing`` = it
listed one and the file is gone; ``expected_output_invalid`` = the file is there and
its ``expected_output`` is not an object (an empty template, or a shape the schema
no longer matches).
"""


class GoldenSeedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    reason: GoldenSeedReason


class GoldenSeedPlan(BaseModel):
    """What seeding a Run into a skill's golden would write, and into which baseline.

    ``files`` is empty when every agent node already has a usable golden, which is the
    common case after the first Run: F6 seeds the gaps, it does not re-promote.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_id: str
    baseline_ref: str | None = None
    baseline_locked: bool = False
    seeded: list[GoldenSeedTarget] = Field(default_factory=list)
    files: list[GoldenBaselineFile] = Field(default_factory=list)


class SetGoldenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    lock: bool
    node_id: str | None = None


class SeedGoldenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str


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
