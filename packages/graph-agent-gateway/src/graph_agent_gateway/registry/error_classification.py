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
    if _has_network_failure(exc):
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
    for item in _exception_chain(exc):
        direct_status_code = getattr(item, "status_code", None)
        if isinstance(direct_status_code, int):
            return direct_status_code
        response = getattr(item, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
    return None


def _has_network_failure(exc: BaseException) -> bool:
    return any(
        isinstance(item, httpx.ConnectError | httpx.TimeoutException)
        for item in _exception_chain(exc)
    )


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain
