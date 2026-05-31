"""Studio LLM registry DTOs.

Studio stores endpoint/route credentials separately from role/profile
authoring data. The executable schema is owned by
``graph_agent_gateway.registry``; this module only adds thin file wrappers
and API-facing helper models.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EffectiveRuntimeSetting,
    EndpointCandidate,
    FieldSource,
    LintResult,
    ProbeResult,
    ProviderImportDraft,
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RoleRouteEntry,
    RouteCandidate,
    RuntimePolicy,
    RuntimeSettingDescriptor,
)
from graph_agent_gateway.registry.schema import (
    ModelProfile as GatewayModelProfile,
)
from graph_agent_gateway.registry.schema import (
    ProviderEndpoint as GatewayProviderEndpoint,
)
from graph_agent_gateway.registry.schema import (
    ProviderRoute as GatewayProviderRoute,
)
from graph_agent_gateway.registry.schema import (
    RoleEntry as GatewayRoleEntry,
)
from graph_agent_gateway.registry.storage import compute_credential_fingerprint
from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderType = Literal["anthropic_compatible", "openai_compatible", "google_genai", "ark_runtime"]

TestStatus = Annotated[
    Literal[
        "untested",
        "ok",
        "invalid_key",
        "rate_limited",
        "quota_exceeded",
        "network_error",
        "timeout",
        "error",
    ],
    Field(description="Provider/route probe status for API responses."),
]


class ModelInfo(BaseModel):
    """One provider-advertised model used by probe helpers."""

    model_config = ConfigDict(extra="forbid")

    id: str
    capabilities: dict[str, object] = Field(default_factory=dict)


class ProviderEndpoint(GatewayProviderEndpoint):
    """Studio-owned endpoint DTO with user-facing provider label."""

    display_name: str


class ProviderRoute(GatewayProviderRoute):
    """Studio-owned route DTO with optional admin/display label."""

    display_name: str | None = None


class ModelProfile(GatewayModelProfile):
    """Studio-owned reusable route bundle with user-facing display label."""

    display_name: str


def _gateway_endpoint(endpoint: ProviderEndpoint) -> GatewayProviderEndpoint:
    return GatewayProviderEndpoint.model_validate(
        endpoint.model_dump(mode="python", exclude={"display_name"})
    )


def _gateway_route(route: ProviderRoute) -> GatewayProviderRoute:
    return GatewayProviderRoute.model_validate(
        route.model_dump(mode="python", exclude={"display_name"})
    )


def _gateway_model_profile(profile: ModelProfile) -> GatewayModelProfile:
    return GatewayModelProfile.model_validate(
        profile.model_dump(mode="python", exclude={"display_name"})
    )


def _gateway_role(role: RoleEntry) -> GatewayRoleEntry:
    return GatewayRoleEntry.model_validate(
        role.model_dump(
            mode="python",
            include={
                "system_prompt_prefix",
                "source_profile_id",
                "fallback_chain",
                "lint_requirements",
            },
        )
    )


class LLMCredentialsFile(BaseModel):
    """Schema stored at the active Studio LLM credentials path."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[4] = 4
    provider_endpoints: dict[str, ProviderEndpoint] = Field(default_factory=dict)
    provider_routes: dict[str, ProviderRoute] = Field(default_factory=dict)
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)

    def endpoint_fingerprint(self, endpoint_id: str) -> str:
        """Return the gateway-owned credential fingerprint for one endpoint."""
        return compute_credential_fingerprint(self.provider_endpoints[endpoint_id])


class RoleTokenIntent(BaseModel):
    """Role-level token intent. Role level cannot inherit from a parent."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["default", "maximum_available", "target", "required_minimum"]
    value: int | None = Field(default=None, ge=1)
    downgrade: Literal["allow", "allow_with_warning", "block"] = "allow"


class TokenIntent(BaseModel):
    """Nested token intent. Model groups may inherit from the role."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["inherit", "default", "maximum_available", "target", "required_minimum"]
    value: int | None = Field(default=None, ge=1)
    downgrade: Literal["allow", "allow_with_warning", "block"] = "allow"


class RoleIntent(BaseModel):
    """User intent stored at the Role level."""

    model_config = ConfigDict(extra="forbid")

    provider_preference: Literal["official_first", "ready_first", "manual_order"] = (
        "official_first"
    )
    thinking: Literal["off", "preferred", "required"] = "off"
    target_context_tokens: RoleTokenIntent | None = None
    target_output_tokens: RoleTokenIntent | None = None
    cost_priority: Literal["quality", "balanced", "low_cost"] | None = None


class ModelGroupIntent(BaseModel):
    """Optional Model Group override intent."""

    model_config = ConfigDict(extra="forbid")

    provider_preference: Literal["official_first", "ready_first", "manual_order"] | None = None
    thinking: Literal["inherit", "off", "preferred", "required"] = "inherit"
    target_context_tokens: TokenIntent | None = None
    target_output_tokens: TokenIntent | None = None
    cost_priority: Literal["quality", "balanced", "low_cost"] | None = None


class RoleProviderModel(BaseModel):
    """One selected provider model option inside a Model Group."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    intent: ModelGroupIntent | None = None


class RoleModelGroup(BaseModel):
    """One user-authored Model Group in a Role."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    display_name: str
    intent: ModelGroupIntent = Field(default_factory=ModelGroupIntent)
    provider_models: list[RoleProviderModel] = Field(default_factory=list)


class RoleEntry(GatewayRoleEntry):
    """Studio Role entry with authoring fields plus generated fallback chain."""

    role_kind: Literal["graph_agent", "copilot"] = "graph_agent"
    model_fallback_enabled: bool = True
    intent: RoleIntent = Field(default_factory=RoleIntent)
    model_groups: list[RoleModelGroup] = Field(default_factory=list)
    materialization_report: dict[str, Any] = Field(
        default_factory=lambda: {
            "entries": [],
            "warnings": [],
            "skipped_provider_details": [],
        }
    )


class ModelBundle(BaseModel):
    """Studio-authored reusable model-group bundle plus generated flat route chain."""

    model_config = ConfigDict(extra="forbid")

    model_profile_id: str
    display_name: str
    canonical_id: str
    tags: list[str] = Field(default_factory=list)
    model_fallback_enabled: bool = True
    intent: RoleIntent = Field(default_factory=RoleIntent)
    model_groups: list[RoleModelGroup] = Field(default_factory=list)
    fallback_chain: list[RoleRouteEntry] = Field(default_factory=list)
    lint_requirements: dict[str, Literal["off", "warn", "error"]] = Field(default_factory=dict)
    materialization_report: dict[str, Any] = Field(
        default_factory=lambda: {
            "entries": [],
            "warnings": [],
            "skipped_provider_details": [],
        }
    )


class RolesData(BaseModel):
    """Schema stored at the active Studio LLM roles path."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2, 3] = 2
    model_profiles: dict[str, ModelProfile] = Field(default_factory=dict)
    model_bundles: dict[str, ModelBundle] = Field(default_factory=dict)
    roles: dict[str, RoleEntry] = Field(default_factory=dict)

    @field_validator("roles", mode="before")
    @classmethod
    def _coerce_gateway_roles(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {
            role_name: role.model_dump(mode="json")
            if hasattr(role, "model_dump") and not isinstance(role, RoleEntry)
            else role
            for role_name, role in value.items()
        }

    def to_registry_snapshot(self, credentials: LLMCredentialsFile) -> RegistrySnapshot:
        """Join credentials and roles into the gateway runtime snapshot."""
        return RegistrySnapshot(
            provider_endpoints={
                endpoint_id: _gateway_endpoint(endpoint)
                for endpoint_id, endpoint in credentials.provider_endpoints.items()
            },
            provider_routes={
                route_id: _gateway_route(route)
                for route_id, route in credentials.provider_routes.items()
            },
            runtime_policy=credentials.runtime_policy,
            model_profiles={
                profile_id: _gateway_model_profile(profile)
                for profile_id, profile in self.model_profiles.items()
            },
            roles={role_name: _gateway_role(role) for role_name, role in self.roles.items()},
        )


class RegistryResponse(BaseModel):
    """Redacted registry response plus grouped display metadata."""

    model_config = ConfigDict(extra="forbid")

    provider_endpoints: dict[str, ProviderEndpoint] = Field(default_factory=dict)
    provider_routes: dict[str, ProviderRoute] = Field(default_factory=dict)
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    model_profiles: dict[str, ModelProfile] = Field(default_factory=dict)
    roles: dict[str, RoleEntry] = Field(default_factory=dict)
    canonical_groups: list[dict[str, object]] = Field(default_factory=list)
    model_groups: list[dict[str, object]] = Field(default_factory=list)
    lint_results: list[LintResult] = Field(default_factory=list)
    route_runtime_settings: dict[str, dict[str, RuntimeSettingDescriptor]] = Field(
        default_factory=dict
    )
    role_effective_runtime_settings: dict[
        str,
        dict[str, dict[str, EffectiveRuntimeSetting]],
    ] = Field(default_factory=dict)
    setup_required: bool = False


__all__ = [
    "CapabilityValue",
    "EndpointCandidate",
    "EffectiveRuntimeSetting",
    "FieldSource",
    "LLMCredentialsFile",
    "LintResult",
    "ModelInfo",
    "ModelBundle",
    "ModelProfile",
    "ProbeResult",
    "ProviderEndpoint",
    "ProviderImportDraft",
    "ProviderRoute",
    "ProviderType",
    "RegistryResponse",
    "RegistrySnapshot",
    "ResolvedRole",
    "ResolvedRoute",
    "RoleEntry",
    "RoleRouteEntry",
    "RolesData",
    "RouteCandidate",
    "RuntimeSettingDescriptor",
    "RuntimePolicy",
    "TestStatus",
]
