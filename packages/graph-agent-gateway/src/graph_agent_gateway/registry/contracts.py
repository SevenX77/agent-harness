"""Control Plane / Runtime Plane contract models."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

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
    """Retry settings for Gateway-owned standard provider terminals."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_ms: list[int] = Field(default_factory=list)
    retryable_status_codes: list[int] = Field(default_factory=list)

    @field_validator("backoff_ms")
    @classmethod
    def _backoff_ms_are_non_negative(cls, value: list[int]) -> list[int]:
        if any(item < 0 for item in value):
            raise ValueError("backoff_ms entries must be non-negative")
        return value

    @field_validator("retryable_status_codes")
    @classmethod
    def _status_codes_are_httpish(cls, value: list[int]) -> list[int]:
        if any(item < 100 or item > 599 for item in value):
            raise ValueError("retryable_status_codes entries must be HTTP status codes")
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
    return StandardTerminalRetrySettings(
        max_attempts=2,
        backoff_ms=[250],
        retryable_status_codes=[429, 500, 502, 503, 504, 529],
    )


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
