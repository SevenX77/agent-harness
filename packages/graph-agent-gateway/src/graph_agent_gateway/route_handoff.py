from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from graph_agent_gateway.registry.schema import ResolvedRoute


class RouteSkipDiagnostic(BaseModel):
    route_id: str
    reason_code: str
    message: str
    from_override: bool

    model_config = ConfigDict(extra="forbid")


class ResolvedRouteChain(BaseModel):
    role: str
    routes: list[ResolvedRoute]
    skipped: list[RouteSkipDiagnostic]
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_routes_or_error(self) -> ResolvedRouteChain:
        if not self.routes:
            if self.error_code != "resource.no_available_route" or not self.error_payload:
                raise ValueError(
                    "Empty route chain requires error_code='resource.no_available_route' and non-empty error_payload"
                )
        return self

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True
        return super().model_dump(*args, **kwargs)
