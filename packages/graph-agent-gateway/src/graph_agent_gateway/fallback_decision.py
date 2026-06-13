from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graph_agent_gateway.route_handoff import ResolvedRouteChain


class FallbackDecision(BaseModel):
    action: Literal["retry_same", "switch_route", "give_up"]
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
            if self.error_code != "fallback.give_up" or not self.error_payload:
                raise ValueError("give_up requires error_code='fallback.give_up' and non-empty error_payload")
        return self


class FallbackDecisionRequest(BaseModel):
    chain: ResolvedRouteChain
    current_route_id: str
    attempt: int
    error_context: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def decide_fallback(request: FallbackDecisionRequest) -> FallbackDecision:
    routes = request.chain.routes
    if not routes:
        return FallbackDecision(
            action="give_up",
            reason_code="all_routes_failed",
            error_code="fallback.give_up",
            error_payload={"role": request.chain.role},
        )

    current_index = -1
    for i, route in enumerate(routes):
        if route.route_id == request.current_route_id:
            current_index = i
            break

    if current_index == -1 or current_index >= len(routes) - 1:
        return FallbackDecision(
            action="give_up",
            reason_code="all_routes_failed",
            error_code="fallback.give_up",
            error_payload={"role": request.chain.role},
        )

    next_route = routes[current_index + 1]
    return FallbackDecision(
        action="switch_route",
        reason_code="switch_to_next_route",
        next_route_id=next_route.route_id,
    )
