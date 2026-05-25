"""Gateway role/config schemas used by the resolver and runtime model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelEntry(BaseModel):
    """Editable model registry entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    reasoning: bool = False
    min_max_tokens: int | None = None
    max_input_tokens: int | None = None
    fc_supported: bool = False
    providers: dict[str, str]
    provider_options: dict[str, dict[str, Any]] | None = None


class ProviderEntry(BaseModel):
    """Editable provider registry entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    api_key_env: str | None = None
    api_key_env_fallback: str | None = None
    base_url: str | None = None
    llm_base_url: str | None = None
    proxy_env: str | None = None
    timeout: int | None = None
    trust_env: bool | None = None
    retry_strategy: str | None = None


class RoleModelEntry(BaseModel):
    """One model entry inside a role fallback chain."""

    model_config = ConfigDict(extra="forbid")

    providers: list[str] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None


class RoleEntry(BaseModel):
    """Editable role registry entry."""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = None
    max_tokens: int | None = None
    model_fallback: bool = False
    active_model: str
    system_prompt_prefix: str | None = None
    models: dict[str, RoleModelEntry] = Field(default_factory=dict)


class RolesData(BaseModel):
    """Full editable LLM roles tree."""

    model_config = ConfigDict(extra="allow")

    models: dict[str, ModelEntry]
    providers: dict[str, ProviderEntry]
    roles: dict[str, RoleEntry]
    single_model_roles: list[str] = Field(default_factory=list)
    peer_model_groups: dict[str, list[str]] = Field(default_factory=dict)
    circuit_breaker: dict[str, Any] | None = None


class ModelDef(BaseModel):
    """Resolved model definition consumed by GatewayChatModel."""

    model_config = ConfigDict(extra="forbid")

    code: str = ""
    name: str
    reasoning: bool = False
    min_max_tokens: int = 4096
    max_input_tokens: int | None = None
    fc_supported: bool = False
    providers: dict[str, str] = Field(default_factory=dict)
    provider_options: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProviderDef(BaseModel):
    """Resolved provider definition consumed by GatewayChatModel."""

    model_config = ConfigDict(extra="forbid")

    code: str = ""
    name: str
    type: str
    api_key_env: str = ""
    api_key_env_fallback: str = ""
    base_url: str = ""
    llm_base_url: str = ""
    proxy_env: str = ""
    timeout: int = 120
    trust_env: bool = False
    retry_strategy: str = ""


class ResolvedProvider(BaseModel):
    """One provider/model candidate in the fallback chain."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider_code: str
    provider_def: ProviderDef
    model_name: str
    model_def: ModelDef
    provider_options: dict[str, Any] = Field(default_factory=dict)


class ResolvedRole(BaseModel):
    """Resolved role fallback chain."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role_name: str
    temperature: float
    system_prompt_prefix: str
    active_model_code: str
    model_fallback: bool
    call_chain: list[ResolvedProvider] = Field(default_factory=list)
