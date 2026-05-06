"""Error and lint issue models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str
    http_status: int
    message: str
    details: dict[str, Any] | None = None
    retry_strategy: Literal["idempotent", "not_retryable", "backoff"]


class LintError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line: int | None = None
    column: int | None = None
    error_code: str
    severity: Literal["error", "warning"]
    message: str
    phase_name: str | None = None
