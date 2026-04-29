"""Pydantic schemas for batch-analysis (V2 Schema Tag pattern).

Only LIST-shaped phase outputs use V2 schemas; composite-output phases
(entity_and_characters / parallel_analysis) keep the legacy ctx-write
tool pattern because their result is naturally an accumulating dict
of multiple categories rather than a homogeneous list.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContinuityWarning(BaseModel):
    """``continuity`` phase output — one cross-batch contradiction note."""

    warning_id: str = Field(description="告警 ID（如 CW_001）")
    dimension: Literal[
        "appearance",
        "prop",
        "spatiotemporal",
        "survival",
        "other",
    ] = Field(description="连续性维度类别")
    severity: Literal["error", "warning", "info"] = Field(
        description="严重程度：error 阻断、warning 提示、info 备查"
    )
    description: str = Field(description="具体矛盾描述（含涉及的 event_id）")
    suggested_fix: str | None = Field(
        default=None, description="建议修法（可选）"
    )
