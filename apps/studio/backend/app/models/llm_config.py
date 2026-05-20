"""Schemas for Studio LLM credential configuration."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

ProviderType = Literal[
    "anthropic_compatible",
    "openai_compatible",
    "google_genai",
]

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
    Field(
        description=(
            "Persisted provider probe status: untested, ok, invalid_key, "
            "rate_limited, quota_exceeded, network_error, timeout, or error."
        )
    ),
]


class ModelInfo(BaseModel):
    """One model advertised or manually confirmed for a provider."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Provider-facing model id, for example gpt-5 or claude-opus-4-7.")
    capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Normalized model capability metadata such as max_context_tokens, "
            "thinking, modalities, or vendor-specific static properties."
        ),
    )


class ProviderCredential(BaseModel):
    """User-configured API credential record persisted in ~/.studio/llm_credentials.json.

    ``id`` is the credential instance lookup dimension. ``provider_key`` is a
    separate metadata lookup dimension in the round 3 design: use it with
    ``model_name`` for vendor/model static properties such as SDK, default
    params, and capabilities. See
    ``.kiro/specs/studio-api-keys-redesign/round3-design.md`` §概念定义.2.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description=(
            "Credential UUID used for credential instance lookup: api_key, "
            "base_url, and Test outcome. Multiple credentials may share the "
            "same provider_key but must have distinct id values."
        ),
    )
    name: str = Field(description="User-facing display name for this credential record.")
    api_key: str = Field(
        default="",
        description=(
            "API authentication secret. In PUT /credentials, an empty string "
            "means preserve the previously stored secret for this id."
        ),
    )
    base_url: str = Field(
        default="",
        description="Provider API base URL override; empty string lets backend defaults apply.",
    )
    provider_type: ProviderType | None = Field(
        default=None,
        description="SDK protocol used to call this credential: anthropic_compatible, openai_compatible, or google_genai.",
    )

    last_test_status: TestStatus = Field(
        default="untested",
        description="Last persisted provider probe status for this credential.",
    )
    last_test_at: str = Field(default="", description="ISO timestamp of the last provider probe, empty when untested.")
    last_test_message: str = Field(default="", description="Human-readable message from the last provider probe.")
    last_error_code: str = Field(default="", description="Machine-readable error code from the last provider probe.")
    available_sdks: list[str] = Field(
        default_factory=list,
        description="SDK protocols confirmed by provider probing for this credential.",
    )
    available_models: list[ModelInfo] = Field(
        default_factory=list,
        description="Models confirmed by automatic or manual probing for this credential.",
    )


TEST_OUTCOME_FIELDS: tuple[str, ...] = (
    "last_test_status",
    "last_test_at",
    "last_test_message",
    "last_error_code",
    "available_sdks",
    "available_models",
)


class LLMCredentialsFile(BaseModel):
    """Schema stored at ``~/.studio/llm_credentials.json``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[3] = 3
    providers: list[ProviderCredential] = Field(default_factory=list)


class ModelEntry(BaseModel):
    """Model registry entry from ``llm_roles.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    reasoning: bool = False
    min_max_tokens: int | None = None
    max_input_tokens: int | None = None
    fc_supported: bool = False
    providers: dict[str, str]
    provider_options: dict[str, dict[str, Any]] | None = None


class ProviderEntry(BaseModel):
    """Provider registry entry from ``llm_roles.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: ProviderType
    api_key_env: str | None = None
    api_key_env_fallback: str | None = None
    base_url: str | None = None
    llm_base_url: str | None = None
    proxy_env: str | None = None
    timeout: int | None = None
    trust_env: bool | None = None
    retry_strategy: str | None = None


class RoleModelEntry(BaseModel):
    """One model entry inside a role's fallback chain."""

    model_config = ConfigDict(extra="forbid")

    providers: list[str] = Field(
        default_factory=list,
        description="Ordered provider identifiers used as the fallback chain for this model in a role.",
    )


class RoleEntry(BaseModel):
    """Role registry entry from ``llm_roles.yaml``."""

    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.7, description="Sampling temperature used when this role invokes a model.")
    model_fallback: bool = Field(default=False, description="Whether this role may fall back across configured models/providers.")
    active_model: str = Field(description="Model code currently selected as the first-choice model for this role.")
    system_prompt_prefix: str | None = Field(default=None, description="Optional role-specific prompt prefix prepended at runtime.")
    models: dict[str, RoleModelEntry] = Field(
        default_factory=dict,
        description="Role model map keyed by model code, each value carrying that model's provider fallback chain.",
    )


class RolesData(BaseModel):
    """Round-trip editable role configuration."""

    model_config = ConfigDict(extra="allow")

    models: dict[str, ModelEntry]
    providers: dict[str, ProviderEntry]
    roles: dict[str, RoleEntry]
    single_model_roles: list[str] = Field(default_factory=list)
    peer_model_groups: dict[str, list[str]] = Field(default_factory=dict)
    circuit_breaker: dict[str, Any] | None = None

    _raw: Any = PrivateAttr(default=None)
    _original_text: str | None = PrivateAttr(default=None)
    _original_snapshot: dict[str, Any] | None = PrivateAttr(default=None)


__all__ = [
    "LLMCredentialsFile",
    "ModelEntry",
    "ModelInfo",
    "ProviderEntry",
    "ProviderCredential",
    "ProviderType",
    "RoleEntry",
    "RoleModelEntry",
    "RolesData",
    "TEST_OUTCOME_FIELDS",
    "TestStatus",
]
