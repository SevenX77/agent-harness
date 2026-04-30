"""Run comparison models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class CompareResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    differences: list[dict[str, Any]]
    score: float
