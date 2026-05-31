"""Pydantic models for Predict V2 internal data exchange."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from graph_agent.core.result import PhaseRecord, PathDiff

class GoldenCase(BaseModel):
    """Persisted backtest case anchored to LLM phase outputs."""

    inputs: dict[str, Any]
    metadata: dict[str, Any] = Field(
        ...,
        description="Contains phase_name, prompt_hash, and io_outputs_schema_hash",
    )
    expected_traces: dict[str, dict[str, Any]] = Field(
        ...,
        description="Mapping of phase_name to expected_output payload",
    )


HeuristicStub = dict[str, Any]


class PredictResult(BaseModel):
    """Predict execution result returned to Studio Backend consumers."""

    status: Literal["success", "failed"]
    phases: list[PhaseRecord]
    path_diff: PathDiff | None = None


__all__ = [
    "GoldenCase",
    "HeuristicStub",
    "PathDiff",
    "PhaseRecord",
    "PredictResult",
]

