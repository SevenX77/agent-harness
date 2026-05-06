"""Run request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from graph_agent.callbacks.events import CallbackEvent


class TokensMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_data: dict[str, Any] | None = None
    golden_id: str | None = None
    paste_json: str | None = None


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["running", "success", "failed"]
    started_at: datetime
    metrics: TokensMetrics | None = None


class RunDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: RunMetadata
    events: list[CallbackEvent]
    final_context: dict[str, Any] | None = None
    artifacts: list[str] | None = None


class ResumeReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_overrides: dict[str, Any] | None = None
    human_input: str | None = None
