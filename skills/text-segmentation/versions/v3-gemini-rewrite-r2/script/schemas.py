"""Pydantic schemas for text segmentation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    """A single classified text segment."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(description="段落顺序编号，从 1 开始递增")
    type: Literal["A", "B", "C"] = Field(description="段落类型 (A=设定, B=事件, C=次元空间)")
    start_line: int = Field(description="该段落起始行号 (包含)")
    end_line: int = Field(description="该段落结束行号 (包含)")
    content: str = Field(description="段落的一句话剧情概括 (50字以内)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="类型判断置信度")
    notes: str | None = Field(default=None, description="修正说明或特殊边界记录 (Review 阶段专用)")


class SegmentationResult(BaseModel):
    """Complete segmentation list output format."""

    model_config = ConfigDict(extra="forbid")

    segments: list[Segment] = Field(
        min_length=1,
        description=(
            "切分后的段落列表。**禁止提交空列表**——必须至少包含 1 个 segment。"
            "若 LLM 提交空 segments 会导致 Pydantic 校验失败 + nudge retry。"
        ),
    )
