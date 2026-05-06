"""Typed workflow result contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowMetrics(BaseModel):
    """Token and timing metrics for a workflow run."""

    model_config = ConfigDict(extra="allow")

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wall_time_sec: float = 0.0

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, wall_time_sec: float) -> "WorkflowMetrics":
        """Build metrics while preserving legacy token keys as extras."""
        input_tokens = int(raw.get("input_tokens", raw.get("total_input_tokens", 0)) or 0)
        output_tokens = int(raw.get("output_tokens", raw.get("total_output_tokens", 0)) or 0)
        total_tokens = int(raw.get("total_tokens", input_tokens + output_tokens) or 0)
        data = dict(raw)
        data.setdefault("total_input_tokens", input_tokens)
        data.setdefault("total_output_tokens", output_tokens)
        data.update(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            wall_time_sec=float(raw.get("wall_time_sec", wall_time_sec) or 0.0),
        )
        return cls(**data)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class WorkflowResult(BaseModel):
    """Typed result returned by graph_agent.run_skill."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    run_id: str
    skill_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    metrics: WorkflowMetrics = Field(default_factory=WorkflowMetrics)
    trace_path: Path | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime
    wall_time_sec: float = 0.0

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
