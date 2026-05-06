"""Run comparison models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


FieldDiffType = Literal["text", "number", "bool", "list", "dict", "null", "unknown"]


class FieldDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    type: FieldDiffType
    current_value: Any
    golden_value: Any
    score: float
    changed: bool


class CompareResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    differences: list[FieldDifference]
    total_score: float
    golden_run_id: str
