"""What one route looks like to whoever is reading the registry.

Six states, derived from what is stored about the endpoint, the route and the
credential — never from a live call. Turning that projection into a role's
runnable chain is a different question with a different owner: see
``graph_agent_gateway.role``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graph_agent_gateway.registry.schema import ProviderRoute, ProviderUiState


class ProviderModelStateProjection(BaseModel):
    route_id: str
    ui_state: ProviderUiState
    reason_code: Literal["missing_config", "endpoint_unreachable", "model_failed"] | None = None
    retry_at: datetime | None = None
    ui_detail: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_ui_state_reason(self) -> ProviderModelStateProjection:
        if self.ui_state != "failed":
            if self.reason_code is not None:
                raise ValueError(f"reason_code must be None when ui_state is '{self.ui_state}'")
        else:
            if self.reason_code is None:
                raise ValueError("reason_code must be provided when ui_state is 'failed'")
        return self


def project_route_state(
    *,
    route_id: str,
    endpoint_status: str,
    route_status: str,
    credential_available: bool,
    circuit_retry_at: datetime | None = None,
    credential_evidence_refs: list[str] | None = None,
) -> ProviderModelStateProjection:
    evidence_refs = [
        ref for ref in credential_evidence_refs or [] if isinstance(ref, str)
    ]

    if endpoint_status == "disabled" or route_status == "disabled":
        return ProviderModelStateProjection(route_id=route_id, ui_state="off")

    if not credential_available:
        return ProviderModelStateProjection(
            route_id=route_id, ui_state="failed", reason_code="missing_config"
        )

    if route_status == "failed":
        return ProviderModelStateProjection(
            route_id=route_id, ui_state="failed", reason_code="model_failed"
        )

    if circuit_retry_at is not None:
        return ProviderModelStateProjection(
            route_id=route_id, ui_state="cooling_down", retry_at=circuit_retry_at
        )

    if endpoint_status == "verified" and route_status == "verified":
        return ProviderModelStateProjection(route_id=route_id, ui_state="ready")

    if evidence_refs:
        return ProviderModelStateProjection(
            route_id=route_id,
            ui_state="historical_ready",
            evidence_refs=evidence_refs,
        )

    if endpoint_status == "failed":
        return ProviderModelStateProjection(
            route_id=route_id, ui_state="failed", reason_code="endpoint_unreachable"
        )

    return ProviderModelStateProjection(route_id=route_id, ui_state="untested")


def project_provider_route_ui_state(
    route: ProviderRoute,
    projection: ProviderModelStateProjection,
) -> ProviderRoute:
    if route.route_id != projection.route_id:
        raise ValueError(
            f"projection route_id '{projection.route_id}' does not match route '{route.route_id}'"
        )
    return route.model_copy(update={"ui_state": projection.ui_state})

