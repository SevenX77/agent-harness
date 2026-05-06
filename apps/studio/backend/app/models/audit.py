"""Intent drift audit models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drift_score: float
    violations: list[str]
