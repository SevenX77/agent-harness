"""Schemas for Studio LLM credential configuration."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

ProviderType = Literal[
    "anthropic_compatible",
    "openai_compatible",
    "gemini_official",
    "wavespeed_any_llm",
]

TestStatus = Literal[
    "untested",
    "ok",
    "invalid_key",
    "rate_limited",
    "quota_exceeded",
    "network_error",
    "timeout",
]


class ModelCapabilities(BaseModel):
    """Per-model capability flags (lightweight, vendor-neutral)."""

    model_config = ConfigDict(extra="forbid")

    text: bool = True
    function_calling: bool = False
    vision: bool = False
    reasoning: bool = False


class ModelInfo(BaseModel):
    """One model advertised by a provider."""

    model_config = ConfigDict(extra="forbid")

    id: str
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)


class ProviderCredential(BaseModel):
    """Local credential entry for one configured LLM provider."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    api_key: str = ""
    base_url: str = ""
    provider_type: ProviderType | None = None

    last_test_status: TestStatus = "untested"
    last_test_at: str = ""
    last_test_message: str = ""
    last_error_code: str = ""
    available_models: list[ModelInfo] = Field(default_factory=list)


TEST_OUTCOME_FIELDS: tuple[str, ...] = (
    "last_test_status",
    "last_test_at",
    "last_test_message",
    "last_error_code",
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

    providers: list[str] = Field(default_factory=list)


class RoleEntry(BaseModel):
    """Role registry entry from ``llm_roles.yaml``."""

    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.7
    model_fallback: bool = False
    active_model: str
    system_prompt_prefix: str | None = None
    models: dict[str, RoleModelEntry] = Field(default_factory=dict)


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
    "ModelCapabilities",
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
