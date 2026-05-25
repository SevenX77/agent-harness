"""Studio LLM registry DTOs.

Studio stores endpoint/route credentials separately from role/profile
authoring data. The executable schema is owned by
``graph_agent_gateway.registry``; this module only adds thin file wrappers
and API-facing helper models.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EndpointCandidate,
    FieldSource,
    LintResult,
    ModelProfile,
    ProbeResult,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RoleEntry,
    RoleRouteEntry,
    RouteCandidate,
    RuntimePolicy,
)
from graph_agent_gateway.registry.storage import compute_credential_fingerprint

ProviderType = Literal["anthropic_compatible", "openai_compatible", "google_genai"]

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


class LLMCredentialsFile(BaseModel):
    """Schema stored at ``~/.studio/llm_credentials.json``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[4] = 4
    provider_endpoints: dict[str, ProviderEndpoint] = Field(default_factory=dict)
    provider_routes: dict[str, ProviderRoute] = Field(default_factory=dict)
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)

    def endpoint_fingerprint(self, endpoint_id: str) -> str:
        """Return the gateway-owned credential fingerprint for one endpoint."""
        return compute_credential_fingerprint(self.provider_endpoints[endpoint_id])


class RolesData(BaseModel):
    """Schema stored at ``config/llm_roles.yaml``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    model_profiles: dict[str, ModelProfile] = Field(default_factory=dict)
    roles: dict[str, RoleEntry] = Field(default_factory=dict)

    def to_registry_snapshot(self, credentials: LLMCredentialsFile) -> RegistrySnapshot:
        """Join credentials and roles into the gateway runtime snapshot."""
        return RegistrySnapshot(
            provider_endpoints=credentials.provider_endpoints,
            provider_routes=credentials.provider_routes,
            runtime_policy=credentials.runtime_policy,
            model_profiles=self.model_profiles,
            roles=self.roles,
        )


class RegistryResponse(RegistrySnapshot):
    """Redacted registry response plus grouped display metadata."""

    canonical_groups: list[dict[str, object]] = Field(default_factory=list)
    lint_results: list[LintResult] = Field(default_factory=list)


__all__ = [
    "CapabilityValue",
    "EndpointCandidate",
    "FieldSource",
    "LLMCredentialsFile",
    "LintResult",
    "ModelInfo",
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
    "RuntimePolicy",
    "TestStatus",
]
