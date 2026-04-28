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
