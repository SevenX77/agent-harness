"""Pydantic schemas for global-synthesis (V2 Schema Tag pattern).

Only the ``retroactive`` phase has a list-shaped output suitable for
V2; ``global_analysis`` produces composite rankings via tool calls
(rank_climaxes / close_foreshadowing / rank_characters) and stays on
the legacy ctx-write pattern.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RetroactiveCorrection(BaseModel):
    """``retroactive`` phase output — one inferred-field correction."""

    event_id: str = Field(description="被修正的事件 ID")
    field: Literal[
        "clothing",
        "makeup",
        "hygiene",
        "injuries",
        "key_relationships",
        "social_position",
        "normalized_location",
        "lighting_vibe",
        "absolute_date",
    ] = Field(description="被修正的字段名")
    corrected_value: str = Field(description="修正后的取值")
    anchor_event_id: str = Field(description="提供锚定事实的事件 ID")
    reason: str = Field(description="修正依据，简短说明锚定事实")


class GlobalSynthesisReport(BaseModel):
    """Phase 3 M7 (PHASE3_DESIGN.md §3.3) — minimal schema for the
    ``global_analysis`` and ``retroactive`` LLM phases.

    These two phases historically called ``finish_task`` without an
    ``output_schema``. Their substantive work happens through
    ``rank_climaxes`` / ``rank_characters`` / ``apply_retroactive_*``
    agent_tools that mutate the ctx, so this schema captures only the
    minimum acknowledgement required by the new
    ProtocolValidation+CognitiveFlow pipeline: a free-text global
    insight summary, plus an integer count of retroactive corrections
    (kept across both phases for shape uniformity).
    """

    global_insights: str = Field(
        description="全局综合分析的核心洞察（自由文本，包括关键观察与结论）",
    )
    retroactive_corrections_applied: int = Field(
        default=0,
        ge=0,
        description="本阶段实施的回溯修正次数（global_analysis phase 通常返回 0）",
    )
