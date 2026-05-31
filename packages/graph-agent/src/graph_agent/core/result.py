"""Typed workflow result contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from graph_agent.core.exceptions import ErrorPayload


class WorkflowMetrics(BaseModel):
    """Token and timing metrics for a workflow run."""

    model_config = ConfigDict(extra="allow")

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wall_time_sec: float = 0.0

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, wall_time_sec: float) -> WorkflowMetrics:
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


class PathDiff(BaseModel):
    """Diagnostic comparison between expected and actual execution paths."""

    expected_path: list[str]
    actual_path: list[str]
    missing: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)
    order_mismatch: bool = False


class PhaseRecord(BaseModel):
    """Audit log record for a single executed phase."""

    phase_name: str
    type: Literal["logic", "llm"]
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    mocked_source: Literal["golden_case", "copilot", "heuristic_stub", "manual"] | None = None


class RunResult(BaseModel):
    """Canonical type-safe result returned by graph_agent runs and predictions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    run_id: str
    skill_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    metrics: WorkflowMetrics = Field(default_factory=WorkflowMetrics)
    trace_path: Path | None = None
    error: ErrorPayload | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    wall_time_sec: float = 0.0
    source: Literal["run", "predict"] = "run"
    phases: list[PhaseRecord] | None = None
    path_diff: PathDiff | None = None

    @property
    def status(self) -> Literal["success", "failed"]:
        return "success" if self.success else "failed"


class WorkflowResult(RunResult):
    """Deprecated backward-compatible result wrapper with dict-like shims."""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
