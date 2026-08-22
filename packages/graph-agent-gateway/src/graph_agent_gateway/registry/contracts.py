"""Control Plane / Runtime Plane contract models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

if TYPE_CHECKING:
    # Only the annotations below need these, and importing them for real would
    # close a cycle: the schema models are built on this file's contracts.
    from graph_agent_gateway.registry.schema import ProviderEndpoint, ProviderRoute

CredentialStatus = Literal["available", "missing", "disabled", "expired", "scope_denied", "unknown"]


class CredentialDescriptor(BaseModel):
    """Non-secret readiness descriptor returned by a host CredentialProvider."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    exists: bool
    status: CredentialStatus = "unknown"
    fingerprint: str | None = None
    scope: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _availability_is_consistent(self) -> CredentialDescriptor:
        if not self.exists and self.status == "available":
            raise ValueError("available credentials must exist")
        return self


class ActiveCircuit(Protocol):
    """One open circuit, as role materialization reads it.

    Only what the projection consumes is named here: which scope tripped, when
    it may be retried, and what to tell a person. Everything else a host's
    store records (opened_at, failure counts, TTLs) is its own business.
    """

    @property
    def scope(self) -> str: ...

    @property
    def scope_id(self) -> str: ...

    @property
    def retry_at(self) -> datetime: ...

    @property
    def reason_code(self) -> str: ...

    @property
    def message(self) -> str | None: ...


class HealthStore(Protocol):
    """Where open circuits are looked up while a role is resolved.

    A Port, not a base class: circuit persistence is host-owned (Studio's is a
    sqlite file), and resolving a role only ever asks one question of it.
    """

    def get_active_circuits(
        self,
        *,
        route_id: str,
        endpoint_id: str,
        rate_limit_bucket: str,
        now: datetime | None = None,
    ) -> Sequence[ActiveCircuit]: ...


class RouteRegistry(Protocol):
    """Where a route and its endpoint are looked up by id.

    A Protocol rather than a base class because the registry a host keeps is its
    own file: Studio's is an on-disk credentials file carrying a schema version
    and a catalog-sync marker, this package's is ``RegistrySnapshot``, and
    neither should have to become the other to have a route looked up in it.
    Read-only on purpose — resolving a role reads the registry, and anything
    that writes to one is not doing this job.
    """

    @property
    def provider_endpoints(self) -> Mapping[str, ProviderEndpoint]: ...

    @property
    def provider_routes(self) -> Mapping[str, ProviderRoute]: ...


@runtime_checkable
class CredentialProviderProtocol(Protocol):
    """Host callback for credential availability and execution-time secret lookup."""

    def describe(self, ref: str) -> CredentialDescriptor:
        """Return non-secret credential status for config/readiness paths."""

    def get(self, ref: str) -> SecretStr | str:
        """Return a secret only at execution time."""


class SecretLifetimePolicy(BaseModel):
    """Policy for secret-bearing runtime objects kept in process memory."""

    model_config = ConfigDict(extra="forbid")

    standard_client_cache_ttl_seconds: int | None = Field(default=None, ge=0)
    sdk_session_cache_ttl_seconds: int | None = Field(default=None, ge=0)
    invalidate_on_rotation: bool = True
    invalidate_on_logout: bool = True
    invalidate_on_workspace_switch: bool = True
    invalidate_on_endpoint_delete: bool = True
    diagnostics_must_redact: bool = True


class StandardTerminalRetrySettings(BaseModel):
    """How many times a Gateway-owned standard terminal may ask, and how it waits.

    ``max_attempts`` counts ASKS, so 1 means "never retry" and 2 means "one
    retry"; ``backoff_ms`` holds the gaps between them, one per gap.

    WHICH failures are retryable is deliberately not a field here.
    :func:`graph_agent_gateway.resolve.classify_exception` already decides that,
    and it decides more than a status list can express — a connection that never
    reached the provider has no status code at all. A second list here would be
    a second answer to one question, and the two would drift.
    """

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_ms: list[int] = Field(default_factory=list)

    @field_validator("backoff_ms")
    @classmethod
    def _backoff_ms_are_non_negative(cls, value: list[int]) -> list[int]:
        if any(item < 0 for item in value):
            raise ValueError("backoff_ms entries must be non-negative")
        return value

    @model_validator(mode="after")
    def _backoff_shape_matches_attempts(self) -> StandardTerminalRetrySettings:
        if self.backoff_ms and len(self.backoff_ms) != self.max_attempts - 1:
            raise ValueError("backoff_ms length must equal max_attempts - 1 when provided")
        return self


class SdkTerminalRetrySettings(BaseModel):
    """Retry settings passed to SDK terminals implemented by client integrations."""

    model_config = ConfigDict(extra="forbid")

    claude_code_max_retries: int = Field(default=0, ge=0, le=10)


def _standard_runtime_retry_settings() -> StandardTerminalRetrySettings:
    return StandardTerminalRetrySettings(max_attempts=2, backoff_ms=[250])


def _standard_probe_retry_settings() -> StandardTerminalRetrySettings:
    return StandardTerminalRetrySettings(max_attempts=1)


class TerminalRetryPolicy(BaseModel):
    """Deterministic terminal retry defaults from the v1.1 platform design."""

    model_config = ConfigDict(extra="forbid")

    standard_runtime: StandardTerminalRetrySettings = Field(
        default_factory=_standard_runtime_retry_settings
    )
    standard_probe: StandardTerminalRetrySettings = Field(
        default_factory=_standard_probe_retry_settings
    )
    sdk_runtime: SdkTerminalRetrySettings = Field(
        default_factory=lambda: SdkTerminalRetrySettings(claude_code_max_retries=2)
    )
    sdk_probe: SdkTerminalRetrySettings = Field(
        default_factory=lambda: SdkTerminalRetrySettings(claude_code_max_retries=1)
    )


class SnapshotVersion(BaseModel):
    """Version stamps carried by a materialized runtime snapshot."""

    model_config = ConfigDict(extra="forbid")

    registry_version: str | None = None
    catalog_version: str | None = None
    client_id: str | None = None
    client_version: str | None = None
    terminal_version: str | None = None
    probe_contract_version: str | None = None
    client_route_profile_version: str | None = None
    generated_at: str | None = None
