from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class ParagraphSegment(BaseModel):
    """单个 ABC 分段段落."""

    index: int = Field(..., description="段落编号（1-based）")
    type: str = Field(..., description="段落类型（A/B/C）")
    content: str = Field(..., description="段落内容（完整）")
    start_line: int = Field(..., description="起始行号（0-indexed）")
    end_line: int = Field(..., description="结束行号")
    description: str = Field(default="", description="段落描述")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """验证段落类型只能是A/B/C."""
        if v not in ["A", "B", "C"]:
            logger.warning(f"无效的段落类型: {v}，自动修正为B")
            return "B"
        return v


class SegmentationResult(BaseModel):
    """章节分段输出."""

    chapter_number: int = Field(..., description="章节号")
    total_paragraphs: int = Field(..., description="总段落数")
    paragraphs: list[ParagraphSegment] = Field(..., description="段落列表")
    metadata: dict[str, object] = Field(default_factory=dict, description="元数据")


class EventEntry(BaseModel):
    """事件条目."""

    # Core fields
    event_id: str = Field(..., description="事件ID")
    event_summary: str = Field(..., description="事件摘要")
    event_type: str = Field(..., description="事件类型（B/C）")
    paragraph_indices: list[int] = Field(..., description="包含的段落编号")
    location: str = Field(default="位置未明确", description="地点")
    location_change: str | None = Field(default=None, description="地点变化（相对上一事件）")
    time: str = Field(default="时间未明确", description="时间")
    time_change: str | None = Field(default=None, description="时间变化（相对上一事件）")
    setting: list[dict[str, str]] = Field(default_factory=list, description="设定数组")
    is_inferred: list[str] = Field(default_factory=list, description="推断字段列表")

    # Climax & Emotion
    climax_type: str = Field(default="", description="高潮类型")
    climax_desc: str = Field(default="", description="高潮描述")
    emotion_type: str = Field(default="", description="情感类型")
    emotion_desc: str = Field(default="", description="情感描述")
    climax_intensity: float = Field(default=0.0, description="高潮强度")
    emotion_intensity: float = Field(default=0.0, description="情感强度")

    # Batch analysis extension fields
    characters_involved: list[str] = Field(default_factory=list, description="涉及角色")
    props_involved: list[str] = Field(default_factory=list, description="涉及道具")
    arc_moments: list[dict] = Field(default_factory=list, description="弧光时刻")
    foreshadowing_plant: list[str] = Field(default_factory=list, description="伏笔")
    foreshadowing_payoff: list[str] = Field(default_factory=list, description="呼应")
    time_coordinate: dict = Field(default_factory=dict, description="时间坐标")
    normalized_location: str = Field(default="", description="标准化地点")
    scene_space_type: str = Field(default="", description="场景空间类型")
    character_states: list[dict] = Field(default_factory=list, description="角色状态")
    character_changes: list[dict] = Field(default_factory=list, description="角色变化")
    prop_changes: list[dict] = Field(default_factory=list, description="道具变化")
    lighting_vibe: str = Field(default="", description="光影氛围")
    system_change: dict | None = Field(default=None, description="系统变化")
    entity_ids: dict = Field(default_factory=dict, description="实体ID")
    scene_id: str = Field(default="", description="场景ID")


class EventTimeline(BaseModel):
    """章节事件时间线."""

    chapter_number: int = Field(..., description="章节号")
    total_events: int = Field(..., description="总事件数")
    events: list[EventEntry] = Field(..., description="事件列表")
    metadata: dict[str, object] = Field(default_factory=dict, description="元数据")


@dataclass
class BatchAccumulator:
    """跨批次状态累加器."""

    # Accumulated lists (all changed to list[dict])
    character_changes: list[dict] = field(default_factory=list)
    prop_changes: list[dict] = field(default_factory=list)
    foreshadowing: list[dict] = field(default_factory=list)
    emotional_arcs: list[dict] = field(default_factory=list)
    system_evolution: list[dict] = field(default_factory=list)
    climax_candidates: list[dict] = field(default_factory=list)

    # Context summaries
    known_characters: list[str] = field(default_factory=list)
    known_props: list[str] = field(default_factory=list)
    open_foreshadowing: list[str] = field(default_factory=list)
    active_arcs: list[str] = field(default_factory=list)

    # Spacetime state
    time_tracker: dict[str, object] = field(
        default_factory=lambda: {"current_day": 1, "current_period": "day", "last_time_desc": ""}
    )
    location_registry: list[dict] = field(default_factory=list)
    current_lighting_vibe: str = field(default="")

    # Dynamic state
    system_parameters: dict[str, object] = field(default_factory=dict)
    character_latest_states: dict[str, dict] = field(default_factory=dict)

    # Entity registry
    entity_registry: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "character_changes": self.character_changes,
            "prop_changes": self.prop_changes,
            "foreshadowing": self.foreshadowing,
            "emotional_arcs": self.emotional_arcs,
            "system_evolution": self.system_evolution,
            "climax_candidates": self.climax_candidates,
            "known_characters": self.known_characters,
            "known_props": self.known_props,
            "open_foreshadowing": self.open_foreshadowing,
            "active_arcs": self.active_arcs,
            "time_tracker": self.time_tracker,
            "location_registry": self.location_registry,
            "current_lighting_vibe": self.current_lighting_vibe,
            "system_parameters": self.system_parameters,
            "character_latest_states": self.character_latest_states,
            "entity_registry": self.entity_registry,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BatchAccumulator:
        """Deserialize from dict."""
        return cls(
            character_changes=d.get("character_changes", []),
            prop_changes=d.get("prop_changes", []),
            foreshadowing=d.get("foreshadowing", []),
            emotional_arcs=d.get("emotional_arcs", []),
            system_evolution=d.get("system_evolution", []),
            climax_candidates=d.get("climax_candidates", []),
            known_characters=d.get("known_characters", []),
            known_props=d.get("known_props", []),
            open_foreshadowing=d.get("open_foreshadowing", []),
            active_arcs=d.get("active_arcs", []),
            time_tracker=d.get(
                "time_tracker", {"current_day": 1, "current_period": "day", "last_time_desc": ""}
            ),
            location_registry=d.get("location_registry", []),
            current_lighting_vibe=d.get("current_lighting_vibe", ""),
            system_parameters=d.get("system_parameters", {}),
            character_latest_states=d.get("character_latest_states", {}),
            entity_registry=d.get("entity_registry", {}),
        )

    def build_context_text(self) -> str:
        """Format accumulated state as Chinese prompt text."""
        lines = ["## 跨批次累积上下文", ""]

        if self.known_characters:
            lines.append(f"**已知角色**: {', '.join(self.known_characters)}")
        if self.known_props:
            lines.append(f"**已知道具**: {', '.join(self.known_props)}")
        if self.current_lighting_vibe:
            lines.append(f"**当前氛围**: {self.current_lighting_vibe}")

        if self.time_tracker:
            tt = self.time_tracker
            time_str = f"第{tt.get('current_day', 1)}天 {tt.get('current_period', 'day')}"
            if tt.get("last_time_desc"):
                time_str += f" ({tt['last_time_desc']})"
            lines.append(f"**时间状态**: {time_str}")

        if self.location_registry:
            loc_names = [
                loc.get("name", str(i))
                for i, loc in enumerate(self.location_registry)
                if isinstance(loc, dict)
            ]
            if loc_names:
                lines.append(f"**地点登记**: {', '.join(loc_names)}")

        if self.open_foreshadowing:
            lines.append(f"**待收伏笔**: {', '.join(str(f) for f in self.open_foreshadowing)}")
        if self.active_arcs:
            lines.append(f"**活跃弧光**: {', '.join(self.active_arcs)}")

        if self.character_changes:
            lines.append(f"**角色变化**: {len(self.character_changes)} 项")
        if self.prop_changes:
            lines.append(f"**道具变化**: {len(self.prop_changes)} 项")

        if self.character_latest_states:
            char_states = [f"{k}: {v}" for k, v in list(self.character_latest_states.items())[:3]]
            lines.append(f"**角色最新状态**: {'; '.join(char_states)}")

        if self.system_parameters:
            sys_params = [f"{k}={v}" for k, v in list(self.system_parameters.items())[:3]]
            lines.append(f"**系统参数**: {'; '.join(sys_params)}")

        return "\n".join(lines) if len(lines) > 2 else ""
