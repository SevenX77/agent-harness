from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from graph_agent_gateway.registry.error_classification import (
    ErrorActionClassification,
    ErrorContext,
    StreamPhase,
    classify_error_context,
)
from graph_agent_gateway.route_handoff import ResolvedRouteChain


class FallbackDecision(BaseModel):
    action: Literal["retry_same", "switch_route", "give_up", "fail_fast"]
    reason_code: str
    next_route_id: str | None = None
    retry_after: datetime | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_action_fields(self) -> FallbackDecision:
        if self.action == "switch_route":
            if not self.next_route_id:
                raise ValueError("switch_route requires next_route_id")
        elif self.action == "give_up":
            if self.error_code != "resource.no_available_route" or not self.error_payload:
                raise ValueError(
                    "give_up requires error_code='resource.no_available_route' and non-empty error_payload"
                )
        elif self.action == "fail_fast":
            if not self.error_code or not self.error_payload:
                raise ValueError("fail_fast requires error_code and non-empty error_payload")
        return self


class FallbackDecisionRequest(BaseModel):
    chain: ResolvedRouteChain | None = None
    route_ids: list[str] = Field(default_factory=list)
    role: str | None = None
    current_route_id: str
    attempt: int = 1
    failed_route_ids: list[str] = Field(default_factory=list)
    error_context: dict[str, Any] = Field(default_factory=dict)
    retryable_status_codes: set[int] = Field(
        default_factory=lambda: {429, 500, 502, 503, 504, 529}
    )

    model_config = ConfigDict(extra="forbid")


def decide_fallback(request: FallbackDecisionRequest) -> FallbackDecision:
    route_ids = _route_ids(request)
    if not route_ids:
        return _give_up(request, route_ids)

    failed_route_ids = set(request.failed_route_ids)
    classification = _classification(request)
    if classification.action == "fail_request":
        return _fail_fast(request, classification)

    if (
        classification.action == "retry_same_route"
        and request.current_route_id not in failed_route_ids
    ):
        return FallbackDecision(
            action="retry_same",
            reason_code="classification_retry_same_route",
            next_route_id=request.current_route_id,
        )

    next_route_id = _next_route_id(request, route_ids, failed_route_ids)
    if next_route_id is None:
        return _give_up(request, route_ids)

    return FallbackDecision(
        action="switch_route",
        reason_code="classification_fallback_route",
        next_route_id=next_route_id,
    )


def _route_ids(request: FallbackDecisionRequest) -> list[str]:
    if request.route_ids:
        return request.route_ids
    if request.chain is None:
        return []
    return [route.route_id for route in request.chain.routes]


def _role(request: FallbackDecisionRequest) -> str | None:
    if request.role is not None:
        return request.role
    if request.chain is not None:
        return request.chain.role
    return None


def _status_code(error_context: dict[str, Any]) -> int | None:
    raw_status = error_context.get("status_code")
    if raw_status is None:
        raw_status = error_context.get("status")
    if isinstance(raw_status, int):
        return raw_status
    if isinstance(raw_status, str) and raw_status.isdigit():
        return int(raw_status)
    return None


def _classification(request: FallbackDecisionRequest) -> ErrorActionClassification:
    raw = request.error_context.get("classification")
    if raw is None:
        raw = request.error_context.get("error_classification")
    if isinstance(raw, ErrorActionClassification):
        return raw
    if isinstance(raw, dict):
        return ErrorActionClassification.model_validate(raw)

    return classify_error_context(
        _exception_from_error_context(request.error_context),
        ErrorContext(
            route_id=request.current_route_id,
            endpoint_id=_string_context_value(request.error_context, "endpoint_id"),
            credential_ref=_string_context_value(request.error_context, "credential_ref"),
            method_id=_string_context_value(request.error_context, "method_id"),
            request_mapper_id=_string_context_value(request.error_context, "request_mapper_id"),
            provider_error_type=_string_context_value(request.error_context, "provider_error_type")
            or _string_context_value(request.error_context, "error_type"),
            provider_error_message=_string_context_value(request.error_context, "provider_error_message")
            or _string_context_value(request.error_context, "message"),
            status_code=_status_code(request.error_context),
            stream_phase=_stream_phase(request.error_context),
        ),
    )


def _exception_from_error_context(error_context: dict[str, Any]) -> BaseException:
    error_type = str(error_context.get("error_type") or "").lower()
    message = str(error_context.get("message") or error_context.get("provider_error_message") or "provider error")
    if "timeout" in error_type:
        return httpx.TimeoutException(message)
    if "connect" in error_type or "network" in error_type:
        return httpx.ConnectError(message)
    return RuntimeError(message)


def _string_context_value(error_context: dict[str, Any], key: str) -> str | None:
    value = error_context.get(key)
    return value if isinstance(value, str) and value else None


def _stream_phase(error_context: dict[str, Any]) -> StreamPhase:
    value = error_context.get("stream_phase")
    if value == "before_headers":
        return "before_headers"
    if value == "after_200_sse":
        return "after_200_sse"
    return "non_stream"


def _next_route_id(
    request: FallbackDecisionRequest,
    route_ids: list[str],
    failed_route_ids: set[str],
) -> str | None:
    if request.route_ids:
        candidates = route_ids
    else:
        try:
            current_index = route_ids.index(request.current_route_id)
        except ValueError:
            return None
        candidates = route_ids[current_index + 1 :]

    for route_id in candidates:
        if route_id not in failed_route_ids and route_id != request.current_route_id:
            return route_id
    return None


def _give_up(request: FallbackDecisionRequest, route_ids: list[str]) -> FallbackDecision:
    payload: dict[str, Any] = {"role": _role(request)}
    payload["route_ids"] = route_ids
    payload["failed_route_ids"] = sorted(set(request.failed_route_ids))
    return FallbackDecision(
        action="give_up",
        reason_code="all_routes_failed",
        error_code="resource.no_available_route",
        error_payload=payload,
    )


def _fail_fast(
    request: FallbackDecisionRequest,
    classification: ErrorActionClassification,
) -> FallbackDecision:
    return FallbackDecision(
        action="fail_fast",
        reason_code="classification_fail_request",
        error_code="gateway.fail_fast",
        error_payload={
            "role": _role(request),
            "route_id": request.current_route_id,
            "classification": classification.model_dump(mode="json"),
        },
    )
