"""Handing the gateway's decisions to whoever is listening."""

from __future__ import annotations

import logging
from typing import Any

from graph_agent_gateway.events import LLMRouteDecisionEvent, RouteDecision
from graph_agent_gateway.registry.schema import ResolvedRoute

logger = logging.getLogger(__name__)


def build_route_decision_event(
    *,
    phase_name: str,
    decision: RouteDecision,
    route: ResolvedRoute | None = None,
    reason: str | None = None,
    provider_status_code: int | None = None,
    next_route_id: str | None = None,
    voided_streamed_answer: bool = False,
) -> LLMRouteDecisionEvent:
    """Describe one decision, taking the route's identity off the route itself."""
    return LLMRouteDecisionEvent(
        phase_name=phase_name,
        decision=decision,
        route_id=route.route_id if route is not None else None,
        endpoint_id=route.endpoint_id if route is not None else None,
        provider_model_id=route.provider_model_id if route is not None else None,
        protocol=str(route.protocol) if route is not None else None,
        reason=reason,
        provider_status_code=provider_status_code,
        next_route_id=next_route_id,
        voided_streamed_answer=voided_streamed_answer,
    )


def emit_route_decision_event(
    *,
    callbacks: tuple[Any, ...],
    phase_name: str,
    decision: RouteDecision,
    route: ResolvedRoute | None = None,
    reason: str | None = None,
    provider_status_code: int | None = None,
    next_route_id: str | None = None,
    voided_streamed_answer: bool = False,
) -> None:
    """Announce one decision without letting a listener's failure mask the run's."""
    event = build_route_decision_event(
        phase_name=phase_name,
        decision=decision,
        route=route,
        reason=reason,
        provider_status_code=provider_status_code,
        next_route_id=next_route_id,
        voided_streamed_answer=voided_streamed_answer,
    )
    for callback in callbacks:
        try:
            callback.on_event(event)
        except Exception:
            logger.exception(
                "phase=gateway_tracing action=callback_failed callback=%s",
                type(callback).__name__,
            )
