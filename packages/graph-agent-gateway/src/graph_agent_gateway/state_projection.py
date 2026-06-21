from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graph_agent_gateway.registry.schema import (
    EvidenceRecord,
    ProviderRoute,
    ProviderUiState,
    ResolvedRoute,
)


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


class RouteWarning(BaseModel):
    route_id: str
    warning_code: str
    message: str

    model_config = ConfigDict(extra="forbid")


class MaterializedRole(BaseModel):
    role: str
    fallback_chain: list[ResolvedRoute]
    warnings: list[RouteWarning]
    projections: dict[str, ProviderModelStateProjection]
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_fallback_chain_error(self) -> MaterializedRole:
        if not self.fallback_chain:
            if self.error_code != "resource.no_available_route" or not self.error_payload:
                raise ValueError(
                    "Empty fallback_chain requires error_code='resource.no_available_route' and non-empty error_payload"
                )
        return self


class MaterializeRoleRequest(BaseModel):
    user_id: str
    role: str
    include_diagnostics: bool = True

    model_config = ConfigDict(extra="forbid")


def project_route_state(
    *,
    route_id: str,
    endpoint_status: str,
    route_status: str,
    credential_available: bool,
    circuit_retry_at: datetime | None = None,
    draft_history: bool = False,
) -> ProviderModelStateProjection:
    if endpoint_status == "disabled" or route_status == "disabled":
        return ProviderModelStateProjection(route_id=route_id, ui_state="off")

    if not credential_available:
        return ProviderModelStateProjection(
            route_id=route_id, ui_state="failed", reason_code="missing_config"
        )

    if endpoint_status == "failed":
        return ProviderModelStateProjection(
            route_id=route_id, ui_state="failed", reason_code="endpoint_unreachable"
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

    if endpoint_status == "verified" and draft_history:
        return ProviderModelStateProjection(route_id=route_id, ui_state="historical_ready")

    return ProviderModelStateProjection(route_id=route_id, ui_state="untested")


def project_route_state_from_evidence(
    *,
    route_id: str,
    endpoint_status: str,
    route_status: str,
    credential_available: bool,
    evidence_records: list[EvidenceRecord] | None = None,
    circuit_retry_at: datetime | None = None,
) -> ProviderModelStateProjection:
    evidence_refs = [
        record.evidence_id
        for record in evidence_records or []
        if record.evidence_type == "probe"
        and record.trust_state == "probe-verified"
        and (record.route_id == route_id or record.scope.get("route_id") == route_id)
    ]
    projection = project_route_state(
        route_id=route_id,
        endpoint_status=endpoint_status,
        route_status=route_status,
        credential_available=credential_available,
        circuit_retry_at=circuit_retry_at,
        draft_history=bool(evidence_refs),
    )
    if projection.ui_state != "historical_ready":
        return projection
    return projection.model_copy(update={"evidence_refs": evidence_refs})


def project_provider_route_ui_state(
    route: ProviderRoute,
    projection: ProviderModelStateProjection,
) -> ProviderRoute:
    if route.route_id != projection.route_id:
        raise ValueError(
            f"projection route_id '{projection.route_id}' does not match route '{route.route_id}'"
        )
    return route.model_copy(update={"ui_state": projection.ui_state})


def materialize_role(
    *,
    role: str,
    routes: list[ResolvedRoute],
    projections: dict[str, ProviderModelStateProjection],
) -> MaterializedRole:
    fallback_chain = []
    warnings = []

    for route in routes:
        proj = projections.get(route.route_id)
        if proj is None:
            fallback_chain.append(route)
            continue

        if proj.ui_state in ("failed", "off"):
            continue
        elif proj.ui_state == "cooling_down":
            warnings.append(
                RouteWarning(
                    route_id=route.route_id,
                    warning_code="route.cooling_down",
                    message=f"Route {route.route_id} is cooling down",
                )
            )
        else:
            fallback_chain.append(route)

    if not fallback_chain:
        return MaterializedRole(
            role=role,
            fallback_chain=[],
            warnings=warnings,
            projections=projections,
            error_code="resource.no_available_route",
            error_payload={"role": role},
        )

    return MaterializedRole(
        role=role,
        fallback_chain=fallback_chain,
        warnings=warnings,
        projections=projections,
    )
