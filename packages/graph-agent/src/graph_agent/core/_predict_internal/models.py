"""Pydantic models for Predict V2 internal data exchange."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class PhaseRecord(BaseModel):
    """Flat business trace slice emitted by Predict."""

    phase_name: str
    type: Literal["logic", "llm"]
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    mocked_source: Literal["golden_case", "copilot", "heuristic_stub", "manual"] | None = None


HeuristicStub = dict[str, Any]


class PathDiff(BaseModel):
    """Backtest route comparison between expected and actual phase visits."""

    expected_path: list[str]
    actual_path: list[str]
    missing: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)
    order_mismatch: bool = False


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
