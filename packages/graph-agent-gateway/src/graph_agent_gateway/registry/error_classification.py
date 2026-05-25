"""Fallback/fail-fast error classification."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

Decision = Literal["fallback_allowed", "fail_fast", "fail_fast_with_route_context"]

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
FAIL_FAST_STATUS_CODES = {400, 401, 403, 404, 422}


class ErrorClassification(BaseModel):
    """Structured fallback decision."""

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    error_class: str
    provider_status_code: int | None = None
    route_id: str | None = None
    message: str
    unclassified_default: bool = False


def classify_exception(exc: BaseException, *, route_id: str | None = None) -> ErrorClassification:
    """Classify provider/runtime exceptions for deterministic fallback."""
    status_code = _status_code(exc)
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return _classification("fallback_allowed", exc, route_id, status_code)
    if status_code in RETRYABLE_STATUS_CODES:
        return _classification("fallback_allowed", exc, route_id, status_code)
    if status_code in FAIL_FAST_STATUS_CODES:
        return _classification("fail_fast", exc, route_id, status_code)
    return _classification(
        "fail_fast_with_route_context",
        exc,
        route_id,
        status_code,
        unclassified_default=True,
    )


def _classification(
    decision: Decision,
    exc: BaseException,
    route_id: str | None,
    status_code: int | None,
    *,
    unclassified_default: bool = False,
) -> ErrorClassification:
    return ErrorClassification(
        decision=decision,
        error_class=type(exc).__name__,
        provider_status_code=status_code,
        route_id=route_id,
        message=str(exc),
        unclassified_default=unclassified_default,
    )


def _status_code(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None
