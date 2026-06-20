"""Golden baseline models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
    editing. Read-only — the editing write still goes through ``/golden/manual/plan``
    (the Rust native-fs sole writer under D12).
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


class SetGoldenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    lock: bool
    node_id: str | None = None


class GoldenTemplate(BaseModel):
    """N4 atom #33: a schema-valid empty golden template for an agent node.

    Generated from the node's ``io.outputs`` JSON schema so the author can hand-fill
    expected values without a copilot/run source. The output schema serializes under the
    wire key ``schema`` (the Python attribute is ``output_schema`` to avoid shadowing
    ``BaseModel.schema``); ``template`` is the structure-valid empty stub matching it.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    skill_id: str
    node_id: str
    output_schema: dict[str, Any] = Field(alias="schema")
    template: dict[str, Any]


class SetManualGoldenReq(BaseModel):
    """N4 atom #33 manual write: author-defined golden, keyed by node_id, run-less.

    First-class contract distinct from ``SetGoldenReq`` — it carries no ``run_id``
    because a manual golden has no source run; the expected output is author-defined.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    expected_output: dict[str, Any]


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
