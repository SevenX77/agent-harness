"""Run comparison models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FieldDiffType = Literal["text", "number", "bool", "list", "dict", "null", "unknown"]


class FieldDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    type: FieldDiffType
    current_value: Any
    golden_value: Any
    score: float
    changed: bool


NodeGroupStatus = Literal["pass", "fail"]
NodeSchemaStatus = Literal["valid", "stale", "missing"]


class NodeGoldenGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    phase_id: str | None = None
    status: NodeGroupStatus
    score: float
    field_differences: list[FieldDifference] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
    schema_status: NodeSchemaStatus = "valid"
    baseline_ref: str
    run_results_ref: str


class CompareResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_id: str
    source_run_id: str | None = None
    source_run_results_ref: str | None = None
    baseline_ref: str
    run_results_ref: str
    total_score: float
    node_groups: list[NodeGoldenGroup] = Field(default_factory=list)
