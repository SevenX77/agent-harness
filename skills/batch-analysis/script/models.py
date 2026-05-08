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
    suggested_fix: str | None = Field(default=None, description="建议修法（可选）")


class BatchAnalysisReport(BaseModel):
    """Phase 3 M7 (PHASE3_DESIGN.md §3.3) — minimal schema for the three
    batch-analysis LLM phases (``entity_and_characters``,
    ``parallel_analysis``, ``continuity``).

    These phases drive their real work through agent_tools that mutate
    the ctx (``register_entity`` / ``analyze_*`` / ``check_continuity``
    etc.), so historically ``finish_task`` was treated as a no-payload
    "done" signal. After M7 every LLM phase that calls ``finish_task``
    must carry a typed schema so the new ProtocolValidation+CognitiveFlow
    pipeline drops the legacy ValidationMiddleware fallback. The schema
    captures a concise narrative (``analysis_summary``), an enumerated
    issue list (``identified_issues``), and a single-word execution
    verdict (``status``) — enough structure for the LLM to acknowledge
    its run completion without forcing a redesign of the per-phase
    tool flow.
    """

    analysis_summary: str = Field(
        description="批次分析的总结（自由文本，覆盖本阶段的核心判断）",
    )
    identified_issues: list[str] = Field(
        default_factory=list,
        description="本阶段识别出的问题清单，逐条说明（无问题时返回空列表）",
    )
    status: Literal["ok", "warning", "error"] = Field(
        description="本阶段的整体执行状态：ok 全过 / warning 有可继续问题 / error 阻断",
    )
