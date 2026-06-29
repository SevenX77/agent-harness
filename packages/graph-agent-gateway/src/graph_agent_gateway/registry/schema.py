"""Registry schema models."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from graph_agent_gateway.registry.contracts import (
    SecretLifetimePolicy,
    SnapshotVersion,
    TerminalRetryPolicy,
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ROUTE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*$")

Protocol = Literal["openai_compatible", "anthropic_compatible", "google_genai", "ark_runtime"]
ProviderKind = Literal["official", "third_party", "custom"]
RouteStatus = Literal["verified", "unverified_manual", "disabled", "failed"]
ProviderUiState = Literal["ready", "historical_ready", "untested", "failed", "cooling_down", "off"]
CapabilitySource = Literal["api_list", "provider_doc", "agent_draft", "manual", "probed_verified"]
EvidenceTrustState = Literal[
    "doc-discovered",
    "provider-list-observed",
    "draft-inferred",
    "probe-verified",
    "probe-failed",
    "deprecated",
    "stale",
]
EvidenceRecordType = Literal[
    "provider_docs",
    "model_docs",
    "model_list_observation",
    "route_candidate",
    "probe",
    "agent_note",
]
LintSeverity = Literal["off", "warn", "warning", "error"]
RuntimeSettingSource = Literal[
    "route_setting",
    "profile_default",
    "route_capability_default",
    "protocol_default",
    "studio_default",
]
DraftStatus = Literal[
    "pending",
    "needs_probe",
    "probing",
    "probed",
    "applying",
    "applied",
    "expired",
    "conflicted",
    "failed",
]


def _validate_slug(value: str, field_name: str) -> str:
    if not SLUG_RE.match(value):
        raise ValueError(f"{field_name} must match {SLUG_RE.pattern}")
    return value


class CapabilityValue(BaseModel):
    """One normalized capability value plus source metadata."""

    model_config = ConfigDict(extra="forbid")

    value: Any
    source: CapabilitySource
    observed_at: str | None = None
    message: str | None = None


class FieldSource(BaseModel):
    """Agent/manual source annotation for a candidate field."""

    model_config = ConfigDict(extra="forbid")

    source: CapabilitySource
    message: str | None = None
    observed_at: str | None = None


class RuntimePolicy(BaseModel):
    """Gateway runtime health/probing policy."""

    model_config = ConfigDict(extra="forbid")

    provider_down_ttl_seconds: int = Field(default=60, ge=0, le=3600)
    probe_timeout_seconds: int = Field(default=5, ge=1, le=120)
    token_escalation_rounds: int = Field(default=2, ge=0, le=10)
    terminal_retry_enabled: bool = False
    terminal_retry_policy: TerminalRetryPolicy = Field(default_factory=TerminalRetryPolicy)
    secret_lifetime_policy: SecretLifetimePolicy = Field(default_factory=SecretLifetimePolicy)


class ReasoningSettings(BaseModel):
    """Provider-neutral reasoning/thinking request settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    effort: str | None = None
    budget_tokens: int | None = Field(default=None, ge=1)


class StructuredOutputSettings(BaseModel):
    """Provider-neutral structured output request settings."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "json_object", "json_schema"] = "none"
    json_schema: dict[str, Any] | None = None
    strict: bool | None = None


class RuntimeSettings(BaseModel):
    """User-authored normalized runtime settings for one route entry."""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    stop_sequences: list[str] | None = None
    seed: int | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    structured_output: StructuredOutputSettings | None = None
    reasoning: ReasoningSettings = Field(default_factory=ReasoningSettings)


class EffectiveRuntimeSetting(BaseModel):
    """One resolver-produced runtime setting value with provenance."""

    model_config = ConfigDict(extra="forbid")

    value: Any
    source: RuntimeSettingSource
    message: str | None = None


class RuntimeSettingDescriptor(BaseModel):
    """Frontend-safe metadata for one normalized runtime setting control."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value_type: Literal["number", "integer", "boolean", "string", "string_list", "object"]
    supported: bool | None = None
    min: float | None = None
    max: float | None = None
    default: Any = None
    allowed_values: list[str] = Field(default_factory=list)
    source: CapabilitySource | Literal["unknown"] = "unknown"
    message: str | None = None


class ProviderEndpoint(BaseModel):
    """One callable endpoint plus credential and protocol metadata."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    protocol: Protocol
    base_url: str
    credential_ref: str | None = None
    api_key: SecretStr | None = None
    status: RouteStatus = "unverified_manual"
    last_test_at: str | None = None
    last_test_message: str | None = None
    provider_kind: ProviderKind = "third_party"
    rate_limit_bucket: str | None = None
    timeout_seconds: int = Field(default=120, ge=1)
    trust_env: bool = False
    proxy_env: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint_id")
    @classmethod
    def _endpoint_id_is_slug(cls, value: str) -> str:
        return _validate_slug(value, "endpoint_id")


class VerifiedProfile(BaseModel):
    """One tested way to invoke a provider model."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    capability: str
    method_id: str
    request_mapper_id: str
    status: Literal["ready", "failed", "catalog_candidate"] = "ready"
    default: bool = False
    fallback_rank: int = Field(default=100, ge=1)
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderRoute(BaseModel):
    """One physical model route on one endpoint."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    endpoint_id: str
    route_slug: str
    provider_model_id: str
    canonical_id: str
    status: RouteStatus = "unverified_manual"
    ui_state: ProviderUiState = "untested"
    snapshot_version: SnapshotVersion | None = None
    capabilities: dict[str, CapabilityValue] = Field(default_factory=dict)
    verified_profiles: list[VerifiedProfile] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint_id")
    @classmethod
    def _endpoint_id_is_slug(cls, value: str) -> str:
        return _validate_slug(value, "endpoint_id")

    @field_validator("route_slug")
    @classmethod
    def _route_slug_is_slug(cls, value: str) -> str:
        return _validate_slug(value, "route_slug")

    @field_validator("route_id")
    @classmethod
    def _route_id_shape(cls, value: str) -> str:
        if not ROUTE_ID_RE.match(value):
            raise ValueError(f"route_id must match {ROUTE_ID_RE.pattern}")
        return value

    @model_validator(mode="after")
    def _route_id_matches_parts(self) -> ProviderRoute:
        expected = f"{self.endpoint_id}:{self.route_slug}"
        if self.route_id != expected:
            raise ValueError(f"route_id must equal endpoint_id:route_slug ({expected})")
        return self


class RoleRouteEntry(BaseModel):
    """One route reference in a role/profile fallback chain."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    runtime_settings_source: Literal["route_setting", "profile_default"] = "route_setting"
    runtime_settings: RuntimeSettings = Field(default_factory=RuntimeSettings)

    @field_validator("route_id")
    @classmethod
    def _route_id_shape(cls, value: str) -> str:
        if not ROUTE_ID_RE.match(value):
            raise ValueError(f"route_id must match {ROUTE_ID_RE.pattern}")
        return value


class RoleEntry(BaseModel):
    """Executable role config using explicit route IDs."""

    model_config = ConfigDict(extra="forbid")

    system_prompt_prefix: str = ""
    source_profile_id: str | None = None
    source_profile_snapshot: dict[str, Any] | None = None
    bundle_id: str | None = None
    fallback_chain: list[RoleRouteEntry] = Field(default_factory=list)
    lint_requirements: dict[str, LintSeverity] = Field(default_factory=dict)

    @field_validator("bundle_id")
    @classmethod
    def _bundle_id_is_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_slug(value, "bundle_id")


class ModelProfile(BaseModel):
    """Authoring-time reusable route bundle."""

    model_config = ConfigDict(extra="forbid")

    model_profile_id: str
    canonical_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    fallback_chain: list[RoleRouteEntry] = Field(default_factory=list)
    lint_requirements: dict[str, LintSeverity] = Field(default_factory=dict)


class ModelBundle(BaseModel):
    """Reusable model bundle referenced by roles during materialization."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    fallback_chain: list[RoleRouteEntry] = Field(default_factory=list)
    lint_requirements: dict[str, LintSeverity] = Field(default_factory=dict)

    @field_validator("bundle_id")
    @classmethod
    def _bundle_id_is_slug(cls, value: str) -> str:
        return _validate_slug(value, "bundle_id")


class EndpointCandidate(ProviderEndpoint):
    """Import-draft endpoint candidate."""

    display_name: str
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)


class RouteCandidate(BaseModel):
    """Import-draft route candidate."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    route_slug: str
    provider_model_id: str
    canonical_id: str
    display_name: str
    capabilities: dict[str, CapabilityValue] = Field(default_factory=dict)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint_id")
    @classmethod
    def _endpoint_id_is_slug(cls, value: str) -> str:
        return _validate_slug(value, "endpoint_id")

    @field_validator("route_slug")
    @classmethod
    def _route_slug_is_slug(cls, value: str) -> str:
        return _validate_slug(value, "route_slug")


class ProbeResult(BaseModel):
    """Endpoint or route probe result stored on an import draft."""

    model_config = ConfigDict(extra="allow")

    target_type: Literal["endpoint", "route"]
    status: Literal["not_run", "running", "success", "failed"]
    observed_at: str | None = None
    capabilities: dict[str, CapabilityValue] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class EvidenceRecord(BaseModel):
    """Append-only evidence about provider docs, candidates, observations, or probes."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_type: EvidenceRecordType
    trust_state: EvidenceTrustState
    observed_at: str | None = None
    attempted_at: str | None = None
    scope: dict[str, str] = Field(default_factory=dict)
    source_url: str | None = None
    provider_docs_url: str | None = None
    model_docs_url: str | None = None
    provider_id: str | None = None
    endpoint_id: str | None = None
    route_id: str | None = None
    model_id: str | None = None
    provider_model_id: str | None = None
    method_id: str | None = None
    request_mapper_id: str | None = None
    probe_status: str | None = None
    reason: str | None = None
    model_type: str | None = None
    capability_family: str | None = None
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    candidate_methods: list[str] = Field(default_factory=list)
    candidate_capabilities: dict[str, CapabilityValue] = Field(default_factory=dict)
    model_list_observation: dict[str, Any] | None = None
    probe_attempts: list[dict[str, Any]] = Field(default_factory=list)
    successful_probe: dict[str, Any] | None = None
    failed_probe: dict[str, Any] | None = None
    agent_note: dict[str, Any] | None = None
    # Studio LLM credentials/catalog SSOT (problem 3): endpoint public identity is a
    # FORMAL field (not metadata) so a locally-built record and one parsed back from
    # the remote catalog hash identically. content_hash is the LOCAL dedup key
    # (credentials de-dup + stable upload candidates); it is never placed on the wire.
    normalized_public_base_url: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def compute_evidence_content_hash(record: EvidenceRecord) -> str:
    """Deterministic content hash keyed only on an evidence record's semantic identity.

    Studio LLM credentials/catalog SSOT (R2.1): the same observation produced at
    different times, on different machines, or locally vs. parsed back from the
    remote catalog yields the SAME hash. Timestamps, api keys, random
    evidence/endpoint ids, display names, and free-form ``metadata`` are excluded so
    they cannot perturb dedup. Used local-side only (credentials de-dup + stable
    upload candidates); it is never placed on the upload/download wire.
    """
    payload: dict[str, str | None] = {
        "evidence_type": record.evidence_type,
        "trust_state": record.trust_state,
        "normalized_public_base_url": record.normalized_public_base_url,
        "provider_model_id": record.provider_model_id,
        "model_id": record.model_id,
        "method_id": record.method_id,
        "request_mapper_id": record.request_mapper_id,
        "probe_status": record.probe_status,
        "capability_family": record.capability_family,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class ProviderImportDraft(BaseModel):
    """Untrusted Agent import draft plus durable advisory evidence."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    source: dict[str, Any]
    status: DraftStatus
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None
    endpoint_candidates: dict[str, EndpointCandidate] = Field(default_factory=dict)
    route_candidates: dict[str, RouteCandidate] = Field(default_factory=dict)
    probe_results: dict[str, ProbeResult] = Field(default_factory=dict)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    agent_notes: list[dict[str, Any]] = Field(default_factory=list)
    diff: dict[str, Any] = Field(default_factory=dict)


class LintResult(BaseModel):
    """One lint result for a route/profile/role."""

    model_config = ConfigDict(extra="forbid")

    role_name: str
    route_id: str
    severity: Literal["warn", "warning", "error"]
    capability: str
    message: str
    source: str
    blocking: bool = False
    code: str | None = None


class RegistrySnapshot(BaseModel):
    """In-memory joined registry snapshot."""

    model_config = ConfigDict(extra="forbid")

    snapshot_version: SnapshotVersion | None = None
    provider_endpoints: dict[str, ProviderEndpoint] = Field(default_factory=dict)
    provider_routes: dict[str, ProviderRoute] = Field(default_factory=dict)
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    model_profiles: dict[str, ModelProfile] = Field(default_factory=dict)
    model_bundles: dict[str, ModelBundle] = Field(default_factory=dict)
    roles: dict[str, RoleEntry] = Field(default_factory=dict)


class ResolvedRoute(BaseModel):
    """One runtime-ready route candidate."""

    model_config = ConfigDict(extra="forbid")

    role_name: str
    route_id: str
    endpoint_id: str
    protocol: Protocol
    base_url: str
    credential_ref: str
    credential_fingerprint: str
    timeout_seconds: int = 120
    trust_env: bool = False
    proxy_env: str | None = None
    provider_model_id: str
    canonical_id: str
    selected_profile_id: str | None = None
    selected_profile_capability: str | None = None
    call_method_id: str | None = None
    request_mapper_id: str | None = None
    capabilities: dict[str, CapabilityValue] = Field(default_factory=dict)
    runtime_settings: RuntimeSettings = Field(default_factory=RuntimeSettings)
    effective_runtime_settings: dict[str, EffectiveRuntimeSetting] = Field(default_factory=dict)
    snapshot_version: SnapshotVersion | None = None

    @model_validator(mode="after")
    def _has_credential_reference(self) -> ResolvedRoute:
        if not self.credential_ref:
            raise ValueError("resolved route requires credential_ref")
        return self


class SkippedRoute(BaseModel):
    """Skipped route diagnostic record."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    reason_code: Literal[
        "route_missing",
        "route_not_executable",
        "endpoint_missing",
        "credential_missing",
        "profile_unavailable",
        "lint_blocked",
    ]
    message: str
    from_override: bool


class ResolvedRole(BaseModel):
    """Resolved role metadata and ordered runtime routes."""

    model_config = ConfigDict(extra="forbid")

    role_name: str
    system_prompt_prefix: str = ""
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    routes: list[ResolvedRoute] = Field(default_factory=list)
    lint_results: list[LintResult] = Field(default_factory=list)
    skipped_diagnostics: list[SkippedRoute] = Field(default_factory=list)
    source_profile_id: str | None = None
    source_profile_snapshot: dict[str, Any] | None = None


class LintRequirement(BaseModel):
    """Normalized lint requirement entry."""

    model_config = ConfigDict(extra="forbid")

    capability: str
    severity: LintSeverity
