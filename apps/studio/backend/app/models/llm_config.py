"""Studio LLM registry DTOs.

Studio stores endpoint/route credentials separately from role/profile
authoring data. The executable schema is owned by
``graph_agent_gateway.registry``; this module only adds thin file wrappers
and API-facing helper models.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from graph_agent_gateway.registry.resolver import materialize_role_entry
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EffectiveRuntimeSetting,
    EndpointCandidate,
    EvidenceRecord,
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
    ModelBundle as GatewayModelBundle,
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
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # W2-B.3: the STRUCTURED failure reason from the last endpoint test (e.g.
    # "invalid_api_key"), so the frontend reads it directly instead of matching the
    # human ``last_test_message`` text. Studio-only presentation field: stripped from
    # the gateway runtime endpoint (see ``_gateway_endpoint``).
    last_error_code: str | None = None
    # W3-B.4: the provider's registrable-domain identity (eTLD+1 of ``base_url``, e.g.
    # "qnaigc" / "wavespeed" / "volces"), so the UI can show the provider id under its
    # display alias. DERIVED from base_url in the registry projection — not persisted
    # truth. Studio-only presentation field: stripped from the gateway runtime endpoint.
    registrable_provider_name: str | None = None


class ProviderRoute(GatewayProviderRoute):
    """Studio-owned route DTO with optional admin/display label."""

    display_name: str | None = None
    # Studio LLM credentials/catalog SSOT: the evidence body lives ON the route —
    # its single persisted home — embedded as the gateway ``EvidenceRecord`` so it
    # is wire-isomorphic with the community catalog. Stripped from the gateway
    # runtime route projection (see ``_gateway_route``).
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    # W2-A status normalization: the route carries the authoritative UI status the
    # frontend reads DIRECTLY — ``ui_state`` (inherited 6-state) plus its companions
    # ``reason_code`` and (for cooling_down) ``retry_at`` — an ISO-8601 timestamp of
    # when the circuit reopens. Stamped by the registry projection so the UI never
    # re-derives a failure scope from message text. Studio-only presentation fields:
    # stripped from the gateway runtime route (see ``_gateway_route``).
    reason_code: str | None = None
    retry_at: str | None = None


class ModelProfile(GatewayModelProfile):
    """Studio-owned reusable route bundle with user-facing display label."""

    display_name: str


def _gateway_endpoint(endpoint: ProviderEndpoint) -> GatewayProviderEndpoint:
    return GatewayProviderEndpoint.model_validate(
        endpoint.model_dump(
            mode="python",
            exclude={"display_name", "last_error_code", "registrable_provider_name"},
        )
    )


def _gateway_route(route: ProviderRoute) -> GatewayProviderRoute:
    return GatewayProviderRoute.model_validate(
        route.model_dump(
            mode="python",
            exclude={"display_name", "evidence", "reason_code", "retry_at"},
        )
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
                "bundle_id",
                "fallback_chain",
                "lint_requirements",
            },
        )
    )


def overlay_bundle_reference_chain(
    role: RoleEntry,
    bundle: ModelBundle,
) -> list[RoleRouteEntry]:
    """Resolve a role's bundle reference into a flat route chain via the gateway.

    #51 (束=引用): delegates the by-reference + delta overlay to the gateway
    resolver's ``materialize_role_entry`` — the canonical owner of that merge. We
    project the role + the already-materialized bundle onto a minimal
    RegistrySnapshot (bundle keyed by its slug) and let the gateway pull the
    bundle's flattened chain and overlay the role's ``fallback_chain`` delta. The
    shell never hand-rolls the merge; this only plumbs the inputs.
    """
    gateway_role = _gateway_role(role)
    snapshot = RegistrySnapshot(
        model_bundles={bundle.model_profile_id: _gateway_model_bundle(bundle)},
        roles={"__reference__": gateway_role},
    )
    merged = materialize_role_entry(snapshot, "__reference__", gateway_role)
    return list(merged.fallback_chain)


def _gateway_model_bundle(bundle: ModelBundle) -> GatewayModelBundle:
    """Project a Studio ModelBundle onto the gateway runtime ModelBundle.

    The Studio bundle is keyed by ``model_profile_id`` which is already a slug
    (#49 generates it via lowercase/underscore normalization); the gateway uses
    that same slug as ``bundle_id`` so a role's ``bundle_id`` reference resolves
    against ``snapshot.model_bundles``. Studio-only authoring fields (display
    name, model_groups, intent, materialization_report) are dropped — the gateway
    only consumes the flattened ``fallback_chain`` + ``lint_requirements``.
    """
    return GatewayModelBundle.model_validate(
        {
            "bundle_id": bundle.model_profile_id,
            "fallback_chain": [entry.model_dump(mode="python") for entry in bundle.fallback_chain],
            "lint_requirements": dict(bundle.lint_requirements),
        }
    )


class RemoteCatalogSyncMarker(BaseModel):
    """Minimal remote verified-catalog sync metadata (Studio SSOT, R1.4).

    Three scalars only — NEVER a full catalog cache, upload queue, or receipt
    history. Updated after a verified sync merges evidence into credentials.
    """

    model_config = ConfigDict(extra="forbid")

    etag: str | None = None
    generated_at: str | None = None
    last_synced_at: str | None = None


class LLMCredentialsFile(BaseModel):
    """Schema stored at the active Studio LLM credentials path."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[5] = 5
    provider_endpoints: dict[str, ProviderEndpoint] = Field(default_factory=dict)
    provider_routes: dict[str, ProviderRoute] = Field(default_factory=dict)
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    last_remote_catalog_sync: RemoteCatalogSyncMarker | None = None

    def endpoint_fingerprint(self, endpoint_id: str) -> str:
        """Return the gateway-owned credential fingerprint for one endpoint."""
        return compute_credential_fingerprint(self.provider_endpoints[endpoint_id])


class RoleTokenIntent(BaseModel):
    """Role-level token intent. Role level cannot inherit from a parent."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["default", "maximum_available", "target"]
    value: int | None = Field(default=None, ge=1)
    downgrade: Literal["allow", "allow_with_warning", "block"] = "allow"

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_required_minimum(cls, value: object) -> object:
        return _migrate_required_minimum_token_intent(value)


class TokenIntent(BaseModel):
    """Nested token intent. Model groups may inherit from the role."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["inherit", "default", "maximum_available", "target"]
    value: int | None = Field(default=None, ge=1)
    downgrade: Literal["allow", "allow_with_warning", "block"] = "allow"

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_required_minimum(cls, value: object) -> object:
        return _migrate_required_minimum_token_intent(value)


class RoleIntent(BaseModel):
    """User intent stored at the Role level."""

    model_config = ConfigDict(extra="forbid")

    provider_preference: Literal["manual_order"] = "manual_order"
    thinking: Literal["off", "preferred", "required"] = "off"
    target_context_tokens: RoleTokenIntent | None = None
    target_output_tokens: RoleTokenIntent | None = None
    cost_priority: Literal["quality", "balanced", "low_cost"] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_provider_preference(cls, value: object) -> object:
        return _migrate_provider_preference(value)


class ModelGroupIntent(BaseModel):
    """Optional Model Group override intent."""

    model_config = ConfigDict(extra="forbid")

    provider_preference: Literal["manual_order"] | None = None
    thinking: Literal["inherit", "off", "preferred", "required"] = "inherit"
    target_context_tokens: TokenIntent | None = None
    target_output_tokens: TokenIntent | None = None
    cost_priority: Literal["quality", "balanced", "low_cost"] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_provider_preference(cls, value: object) -> object:
        return _migrate_provider_preference(value)


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


def _migrate_provider_preference(value: object) -> object:
    if not isinstance(value, dict):
        return value
    if value.get("provider_preference") in {"official_first", "ready_first"}:
        return {**value, "provider_preference": "manual_order"}
    return value


def _migrate_required_minimum_token_intent(value: object) -> object:
    if not isinstance(value, dict):
        return value
    if value.get("mode") != "required_minimum":
        return value
    migrated = dict(value)
    migrated["mode"] = "maximum_available"
    migrated["value"] = None
    return migrated


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
            model_bundles={
                bundle.model_profile_id: _gateway_model_bundle(bundle)
                for bundle in self.model_bundles.values()
            },
            roles={role_name: _gateway_role(role) for role_name, role in self.roles.items()},
        )


class ProbeCatalogSharingSummary(BaseModel):
    """MVP1 probe catalog sharing mode exposed to Studio UI."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["local_export_only"] = "local_export_only"
    auto_upload_enabled: bool = False
    message: str = (
        "Local probe evidence is recorded on this machine. "
        "MVP1 does not auto-upload community catalog evidence."
    )


class CommunityCatalogEntry(BaseModel):
    """One advisory community-verified route surfaced to the Settings UI.

    Sourced from the disposable verified cache; community-observed, never merged
    into local evidence.
    """

    model_config = ConfigDict(extra="forbid")

    public_base_url: str | None = None
    model_id: str | None = None
    capability_family: str | None = None
    method_id: str | None = None
    observed_at: str | None = None


class CommunityCatalogSummary(BaseModel):
    """Verified community catalog (disposable cache) status for Settings UI.

    Advisory only — these records are community-observed and never auto-applied
    to local credentials.
    """

    model_config = ConfigDict(extra="forbid")

    synced: bool = False
    generated_at: str | None = None
    protocol_major: int = 0
    record_count: int = 0
    entries: list[CommunityCatalogEntry] = []


class ProbeCatalogSummary(BaseModel):
    """Local + remote Probe Knowledge Catalog status for Settings UI."""

    model_config = ConfigDict(extra="forbid")

    local_evidence_records_count: int = 0
    local_verified_records_count: int = 0
    local_failed_records_count: int = 0
    local_route_candidates_count: int = 0
    remote_catalog_source: dict[str, Any] | None = None
    community_catalog: CommunityCatalogSummary = Field(default_factory=CommunityCatalogSummary)
    sharing: ProbeCatalogSharingSummary = Field(default_factory=ProbeCatalogSharingSummary)


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
    catalog_source: dict[str, Any] | None = None
    probe_catalog: ProbeCatalogSummary = Field(default_factory=ProbeCatalogSummary)
    role_effective_runtime_settings: dict[
        str,
        dict[str, dict[str, EffectiveRuntimeSetting]],
    ] = Field(default_factory=dict)
    setup_required: bool = False


__all__ = [
    "CapabilityValue",
    "EndpointCandidate",
    "EffectiveRuntimeSetting",
    "EvidenceRecord",
    "FieldSource",
    "LLMCredentialsFile",
    "LintResult",
    "ModelInfo",
    "ModelBundle",
    "ModelProfile",
    "ProbeCatalogSharingSummary",
    "ProbeCatalogSummary",
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
    "overlay_bundle_reference_chain",
]
