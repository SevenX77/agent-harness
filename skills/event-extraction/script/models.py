"""Pydantic schemas for event-extraction phases (V2 Schema Tag pattern).

Each LLM phase declares ``output_schema:`` pointing to one of these
classes; the loader injects ``<output_format>`` into the prompt and
md_to_json parses LLM markdown into validated instances at finish_task.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    """One aggregated story event spanning paragraph_indices.

    Used by the ``aggregate`` phase output. The LLM emits one ``## <id>``
    block per Event; ``_md_id`` becomes the LLM-chosen identifier
    (typically the index or event_id).
    """

    index: int = Field(ge=1, description="事件顺序编号（按时间线排序）")
    type: Literal["B类-事件", "C类-系统"] = Field(
        description="事件类型：B 类是现实事件，C 类是次元/系统事件"
    )
    paragraph_indices: list[int] = Field(
        description="本事件包含的段落索引列表（来自 text-segmentation）"
    )
    location: str = Field(description="地点名（原文位置原词）")
    location_change: str | None = Field(
        default=None, description="相对上一事件的地点变化"
    )
    time: str = Field(description="时间标记（原文时间原词或推断）")
    time_change: str | None = Field(
        default=None, description="相对上一事件的时间关系"
    )
    summary: str = Field(description="事件概括，20-30 字")


class ReviewedEvent(Event):
    """``review`` phase output — Event + audit note."""

    review_notes: str | None = Field(
        default=None, description="审查备注（无修改写'无变化'）"
    )


class Setting(BaseModel):
    """``settings`` phase output — one extracted world-building knowledge entry.

    Setting items are independent of events but cross-reference them via
    ``related_event_id``.
    """

    setting_id: str = Field(description="设定条目 ID（如 SET_001）")
    paragraph_indices: list[int] = Field(
        description="设定知识所在段落索引"
    )
    related_event_id: str = Field(
        description="关联的事件 ID（来自 aggregate/review 输出）"
    )
    core_knowledge: str = Field(
        description="核心知识点（50-100 字精炼）"
    )


class PhaseSummary(BaseModel):
    """Phase 3 M7 (PHASE3_DESIGN.md §3.3) — minimal schema for the
    ``aggregate`` and ``review`` LLM phases.

    These two phases historically called ``finish_task`` without
    declaring an ``output_schema``: their real work happens via
    ``parse_events`` / ``store_events`` agent_tools that mutate the ctx
    directly, and ``finish_task`` was just a "done" signal. After M7
    every LLM phase that uses ``finish_task`` must carry a strongly-
    typed schema so the new ProtocolValidation+CognitiveFlow pipeline
    can drop the ValidationMiddleware fallback. ``summary`` is the
    catch-all field the LLM fills with its analysis narrative.
    """

    summary: str = Field(
        description="本阶段的分析总结（自由文本，含关键判断）",
    )
