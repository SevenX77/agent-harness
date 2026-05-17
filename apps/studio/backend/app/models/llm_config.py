"""Schemas for Studio LLM credential configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class ProviderCredential(BaseModel):
    """Local credential entry for one configured LLM provider."""

    model_config = ConfigDict(extra="forbid")

    provider_code: str
    api_key: str = ""
    base_url: str = ""


class LLMCredentialsFile(BaseModel):
    """Schema stored at ``~/.studio/llm_credentials.json``."""

    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderCredential] = Field(default_factory=list)


ProviderType = Literal[
    "anthropic_compatible",
    "openai_compatible",
    "gemini_official",
    "wavespeed_any_llm",
]


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
    "ModelEntry",
    "ProviderEntry",
    "ProviderCredential",
    "ProviderType",
    "RoleEntry",
    "RoleModelEntry",
    "RolesData",
]
