"""Runtime error action classification plus legacy fallback adapter."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["fallback_allowed", "fail_fast", "fail_fast_with_route_context"]
ErrorAction = Literal["retry_same_route", "fallback_route", "fail_request"]
ErrorScope = Literal["request", "route", "endpoint", "credential", "bucket", "stream", "unknown"]
StreamPhase = Literal["before_headers", "after_200_sse", "non_stream"]

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}
FALLBACK_STATUS_CODES = {401, 402, 403, 404}
FAIL_REQUEST_STATUS_CODES = {400, 413, 422}


class ErrorContext(BaseModel):
    """Provider/runtime context needed for scoped retry and fallback decisions."""

    model_config = ConfigDict(extra="forbid")

    route_id: str | None = None
    endpoint_id: str | None = None
    credential_ref: str | None = None
    method_id: str | None = None
    request_mapper_id: str | None = None
    selected_runtime_settings: dict[str, Any] = Field(default_factory=dict)
    role_requirements: dict[str, Any] = Field(default_factory=dict)
    provider_error_type: str | None = None
    provider_error_message: str | None = None
    status_code: int | None = None
    stream_phase: StreamPhase = "non_stream"


class ErrorActionClassification(BaseModel):
    """Structured v1.1 retry/fallback/fail decision."""

    model_config = ConfigDict(extra="forbid")

    action: ErrorAction
    scope: ErrorScope
    error_class: str
    status_code: int | None = None
    route_id: str | None = None
    endpoint_id: str | None = None
    credential_ref: str | None = None
    method_id: str | None = None
    request_mapper_id: str | None = None
    provider_error_type: str | None = None
    provider_error_message: str | None = None
    message: str
    retryable: bool = False
    fallback_eligible: bool = False
    unclassified_default: bool = False


class ErrorClassification(BaseModel):
    """Structured fallback decision."""

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    error_class: str
    provider_status_code: int | None = None
    route_id: str | None = None
    action: ErrorAction
    scope: ErrorScope
    message: str
    unclassified_default: bool = False


def classify_exception(exc: BaseException, *, route_id: str | None = None) -> ErrorClassification:
    """Classify exceptions for the current Gateway fallback loop.

    The returned decision keeps the legacy enum while exposing the v1.1 action/scope
    for callers that are ready to distinguish terminal retry from route fallback.
    """
    action = classify_error_context(exc, ErrorContext(route_id=route_id))
    decision: Decision
    if action.action in {"retry_same_route", "fallback_route"}:
        decision = "fallback_allowed"
    elif action.unclassified_default:
        decision = "fail_fast_with_route_context"
    else:
        decision = "fail_fast"
    return ErrorClassification(
        decision=decision,
        error_class=action.error_class,
        provider_status_code=action.status_code,
        route_id=action.route_id,
        action=action.action,
        scope=action.scope,
        message=action.message,
        unclassified_default=action.unclassified_default,
    )


def classify_error_context(
    exc: BaseException,
    context: ErrorContext | None = None,
) -> ErrorActionClassification:
    """Classify provider/runtime exceptions into v1.1 action and scope."""
    ctx = context or ErrorContext()
    status_code = ctx.status_code if ctx.status_code is not None else _status_code(exc)
    provider_error_type = ctx.provider_error_type or _provider_error_type(exc)
    provider_error_message = ctx.provider_error_message or _provider_error_message(exc)

    if ctx.stream_phase == "after_200_sse":
        return _action_classification(
            "fallback_route",
            "stream",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
            fallback_eligible=True,
        )
    if _has_network_failure(exc):
        return _action_classification(
            "retry_same_route",
            "route",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
            retryable=True,
        )
    if status_code in RETRYABLE_STATUS_CODES:
        return _action_classification(
            "retry_same_route",
            "bucket" if status_code == 429 else "endpoint",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
            retryable=True,
        )
    if status_code in FALLBACK_STATUS_CODES:
        return _action_classification(
            "fallback_route",
            "route" if status_code == 404 else "credential",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
            fallback_eligible=True,
        )
    if status_code == 400 and _looks_like_route_capability_error(
        provider_error_type,
        provider_error_message,
    ):
        return _action_classification(
            "fallback_route",
            "route",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
            fallback_eligible=True,
        )
    if status_code == 400 and _looks_like_billing_error(
        provider_error_type,
        provider_error_message,
    ):
        # Anthropic encodes account-credit exhaustion as 400 invalid_request_error;
        # semantically it is a 402-class endpoint/billing failure, so the next
        # route (different account/provider) must get its chance.
        return _action_classification(
            "fallback_route",
            "credential",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
            fallback_eligible=True,
        )
    if status_code in FAIL_REQUEST_STATUS_CODES:
        return _action_classification(
            "fail_request",
            "request",
            exc,
            ctx,
            status_code,
            provider_error_type,
            provider_error_message,
        )
    return _action_classification(
        "fail_request",
        "unknown",
        exc,
        ctx,
        status_code,
        provider_error_type,
        provider_error_message,
        unclassified_default=True,
    )


def _action_classification(
    action: ErrorAction,
    scope: ErrorScope,
    exc: BaseException,
    context: ErrorContext,
    status_code: int | None,
    provider_error_type: str | None,
    provider_error_message: str | None,
    *,
    retryable: bool = False,
    fallback_eligible: bool = False,
    unclassified_default: bool = False,
) -> ErrorActionClassification:
    return ErrorActionClassification(
        action=action,
        scope=scope,
        error_class=type(exc).__name__,
        status_code=status_code,
        route_id=context.route_id,
        endpoint_id=context.endpoint_id,
        credential_ref=context.credential_ref,
        method_id=context.method_id,
        request_mapper_id=context.request_mapper_id,
        provider_error_type=provider_error_type,
        provider_error_message=provider_error_message,
        message=str(exc),
        retryable=retryable,
        fallback_eligible=fallback_eligible,
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


def _provider_error_type(exc: BaseException) -> str | None:
    payload = _provider_error_payload(exc)
    value = payload.get("type") or payload.get("code")
    return str(value) if value is not None else None


def _provider_error_message(exc: BaseException) -> str | None:
    payload = _provider_error_payload(exc)
    value = payload.get("message")
    return str(value) if value is not None else None


def _provider_error_payload(exc: BaseException) -> dict[str, object]:
    for item in _exception_chain(exc):
        response = getattr(item, "response", None)
        if response is None:
            continue
        try:
            payload = response.json()
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        error = payload.get("error")
        if isinstance(error, dict):
            return error
        return payload
    return {}


def _looks_like_route_capability_error(
    provider_error_type: str | None,
    provider_error_message: str | None,
) -> bool:
    text = " ".join(
        item.lower()
        for item in (provider_error_type, provider_error_message)
        if item is not None
    )
    return any(
        marker in text
        for marker in (
            "unsupported",
            "not supported",
            "unknown parameter",
            "invalid model",
            "model not found",
        )
    )


def _looks_like_billing_error(
    provider_error_type: str | None,
    provider_error_message: str | None,
) -> bool:
    text = " ".join(
        item.lower()
        for item in (provider_error_type, provider_error_message)
        if item is not None
    )
    return any(
        marker in text
        for marker in (
            "credit balance",
            "insufficient credit",
            "insufficient funds",
            "insufficient quota",
            "purchase credits",
            "billing",
        )
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
