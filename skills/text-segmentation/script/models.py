"""Pydantic schemas for text-segmentation phases.

V2 Schema Tag pattern: SKILL.md declares ``output_schema:
script.models.<Class>``; the loader auto-renders an ``<output_format>``
block in the system prompt, and md_to_json parses the LLM's markdown
output into validated instances of that class.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """One ABC-segmented paragraph block.

    The LLM emits one ``## <index>`` block per Segment. ``md_id`` is
    auto-derived from the markdown header by the parser; the model
    fields below are the canonical JSON shape.
    """

    index: int = Field(ge=1, description="段落顺序编号，从 1 开始递增")
    type: Literal["A", "B", "C"] = Field(
        description="段落类型 A=设定 / B=事件 / C=次元空间"
    )
    start_line: int = Field(ge=1, description="该段落起始行号 (1-based)")
    end_line: int = Field(ge=1, description="该段落结束行号 (1-based)")
    content: str = Field(description="段落剧情概括")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="类型判断置信度 0.0-1.0"
    )
    notes: str | None = Field(default=None, description="特殊边界记录（可选）")
