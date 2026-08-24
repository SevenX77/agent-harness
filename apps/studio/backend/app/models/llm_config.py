"""Studio LLM registry DTOs.

Studio stores endpoint/route credentials separately from role/profile
authoring data. The executable schema is owned by
``graph_agent_gateway.registry``; this module only adds thin file wrappers
and API-facing helper models.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from graph_agent_gateway.registry import (
    CapabilityValue,
    EffectiveRuntimeSetting,
    EndpointCandidate,
    EvidenceRecord,
    FieldSource,
    LintResult,
    LintSeverity,
    ProbeResult,
    ProviderImportDraft,
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RoleRouteEntry,
    RouteCandidate,
    RuntimePolicy,
    RuntimeSettingDescriptor,
    compute_credential_fingerprint,
)
from graph_agent_gateway.registry import (
    ModelBundle as GatewayModelBundle,
)
from graph_agent_gateway.registry import (
    ModelProfile as GatewayModelProfile,
)
from graph_agent_gateway.registry import (
    ProviderEndpoint as GatewayProviderEndpoint,
)
from graph_agent_gateway.registry import (
    ProviderRoute as GatewayProviderRoute,
)
from graph_agent_gateway.registry import (
    RoleEntry as GatewayRoleEntry,
)

# Deliberate re-exports (the ``X as X`` idiom marks them): the role
# authoring model is the gateway's — see
# docs/design/2026-08-13-gateway-role-model-and-section-truth-decision.md —
# and business code keeps importing it from this facade per the SDK import
# boundary (tests/core/adapters/test_productization_import_boundary_red.py).
from graph_agent_gateway.registry import RoleIntent as RoleIntent
from graph_agent_gateway.registry import RoleModelGroup as RoleModelGroup
from graph_agent_gateway.registry import RoleProviderModel as RoleProviderModel
from graph_agent_gateway.resolve import materialize_role_entry
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

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

    @model_validator(mode="before")
    @classmethod
    def _strip_derived_api_key_length(cls, data: Any) -> Any:
        """Drop an incoming ``api_key_length`` so the derivation can never be lied to.

        api_key_length is a pure function of the secret (see the computed field
        below). A client echoing a GET registry payload back into PUT carries it;
        popping it here — instead of leaving ``extra='forbid'`` to reject the whole
        upsert — mirrors the gateway ``ProviderRoute._strip_persisted_canonical_id``
        pattern for computed projections.
        """
        if isinstance(data, dict):
            data.pop("api_key_length", None)
        return data

    # 2026-08-12 决议: the secret's TRUE character count, so the UI masks with the
    # key's real length instead of the SecretStr placeholder's fixed 10 chars.
    # Derived live from the secret (never persisted — see
    # ``_credentials_payload_for_storage``) and stripped from the gateway runtime
    # endpoint like every Studio-only presentation field.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_key_length(self) -> int | None:
        if self.api_key is None:
            return None
        return len(self.api_key.get_secret_value()) or None


class ProviderRoute(GatewayProviderRoute):
    """Studio-owned route DTO with optional admin/display label."""

    display_name: str | None = None
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
            exclude={"display_name", "last_error_code", "registrable_provider_name", "api_key_length"},
        )
    )


def _gateway_route(route: ProviderRoute) -> GatewayProviderRoute:
    return GatewayProviderRoute.model_validate(
        route.model_dump(
            mode="python",
            exclude={"display_name", "reason_code", "retry_at"},
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


class RoleEntry(GatewayRoleEntry):
    """Studio Role entry: the gateway's role plus Studio-only projections.

    The authoring model itself (intent / model groups / fallback toggle) is the
    gateway's — see docs/design/2026-08-13-gateway-role-model-and-section-truth-decision.md.
    """

    role_kind: Literal["graph_agent", "copilot"] = "graph_agent"
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
    lint_requirements: dict[str, LintSeverity] = Field(default_factory=dict)
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
    # No `sharing` projection here: the community-sharing state has exactly one
    # truth (`AppSettings.community_sharing_choice`), fetched via GET /api/settings
    # and already held by the Settings page. A second copy of the same fact
    # projected into this response would be a parallel truth that could drift
    # from the settings toggle (the exact defect this model used to hardcode —
    # see docs/studio/mvp1/01_workflows/00_settings.md §5).


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
