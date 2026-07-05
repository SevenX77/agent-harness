"""Gateway-owned runtime catalog for provider call methods."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Literal, cast

ProviderProbeBackend = Literal["ark", "claude", "deepseek", "gemini", "openai"]
ClientCompatibility = Literal["supported", "incompatible", "unknown"]
BaseUrlTransform = Literal["none", "ark_anthropic_compatible", "deepseek_anthropic"]

_BACKENDS: frozenset[str] = frozenset({"ark", "claude", "deepseek", "gemini", "openai"})
_COMPAT_VALUES: frozenset[str] = frozenset({"supported", "incompatible", "unknown"})
_BASE_URL_TRANSFORMS: frozenset[str] = frozenset(
    {"none", "ark_anthropic_compatible", "deepseek_anthropic"}
)


@dataclass(frozen=True)
class CallMethodDefinition:
    method_id: str
    provider_backend: ProviderProbeBackend
    wire_family: str
    official_probe: bool
    client_compatibility: dict[str, ClientCompatibility]
    base_url_transform: BaseUrlTransform
    auth_token_env: str | None


def call_method_definition(method_id: str) -> CallMethodDefinition | None:
    return _call_method_table().get(method_id)


def official_call_method_ids() -> frozenset[str]:
    return frozenset(
        method_id
        for method_id, definition in _call_method_table().items()
        if definition.official_probe
    )


def call_method_ids_for_client(client_id: str) -> frozenset[str]:
    return frozenset(
        method_id
        for method_id, definition in _call_method_table().items()
        if definition.client_compatibility.get(client_id) == "supported"
    )


def call_method_client_compatibility(method_id: str | None, client_id: str) -> ClientCompatibility:
    if not method_id:
        return "unknown"
    definition = call_method_definition(method_id)
    if definition is None:
        return "unknown"
    return definition.client_compatibility.get(client_id, "unknown")


def provider_probe_backend_for_method(method_id: str) -> ProviderProbeBackend:
    definition = call_method_definition(method_id)
    if definition is None or not definition.official_probe:
        raise ValueError(f"Unknown official call method: {method_id}")
    return definition.provider_backend


def apply_call_method_base_url(method_id: str | None, base_url: str) -> str:
    definition = call_method_definition(method_id or "")
    transform = definition.base_url_transform if definition is not None else "none"
    if transform == "ark_anthropic_compatible":
        return _ark_anthropic_base_url(base_url)
    if transform == "deepseek_anthropic":
        return _deepseek_anthropic_base_url(base_url)
    return base_url.rstrip("/")


def call_method_auth_token_env(method_id: str | None) -> str | None:
    definition = call_method_definition(method_id or "")
    return definition.auth_token_env if definition is not None else None


@lru_cache(maxsize=1)
def _call_method_table() -> dict[str, CallMethodDefinition]:
    raw = json.loads(
        resources.files("graph_agent_gateway.registry")
        .joinpath("call_methods.json")
        .read_text(encoding="utf-8")
    )
    methods = raw.get("methods")
    if not isinstance(methods, list):
        raise ValueError("call_methods.json must contain a methods list")
    table: dict[str, CallMethodDefinition] = {}
    for item in methods:
        if not isinstance(item, dict):
            raise ValueError("call method entry must be an object")
        definition = _definition_from_raw(item)
        if definition.method_id in table:
            raise ValueError(f"Duplicate call method id: {definition.method_id}")
        table[definition.method_id] = definition
    return table


def _definition_from_raw(raw: dict[str, Any]) -> CallMethodDefinition:
    method_id = _required_str(raw, "method_id")
    compat_raw = raw.get("client_compatibility")
    if not isinstance(compat_raw, dict):
        raise ValueError(f"{method_id}: client_compatibility must be an object")
    client_compatibility = {
        str(client_id): _client_compatibility(str(value), method_id)
        for client_id, value in compat_raw.items()
    }
    auth_token_env = raw.get("auth_token_env")
    if auth_token_env is not None and not isinstance(auth_token_env, str):
        raise ValueError(f"{method_id}: auth_token_env must be a string or null")
    return CallMethodDefinition(
        method_id=method_id,
        provider_backend=_provider_backend(_required_str(raw, "provider_backend"), method_id),
        wire_family=_required_str(raw, "wire_family"),
        official_probe=_required_bool(raw, "official_probe"),
        client_compatibility=client_compatibility,
        base_url_transform=_base_url_transform(
            _required_str(raw, "base_url_transform"),
            method_id,
        ),
        auth_token_env=auth_token_env,
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"call method field {key} must be a non-empty string")
    return value


def _required_bool(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"call method field {key} must be a boolean")
    return value


def _provider_backend(value: str, method_id: str) -> ProviderProbeBackend:
    if value not in _BACKENDS:
        raise ValueError(f"{method_id}: unknown provider backend {value}")
    return cast(ProviderProbeBackend, value)


def _client_compatibility(value: str, method_id: str) -> ClientCompatibility:
    if value not in _COMPAT_VALUES:
        raise ValueError(f"{method_id}: unknown client compatibility {value}")
    return cast(ClientCompatibility, value)


def _base_url_transform(value: str, method_id: str) -> BaseUrlTransform:
    if value not in _BASE_URL_TRANSFORMS:
        raise ValueError(f"{method_id}: unknown base_url_transform {value}")
    return cast(BaseUrlTransform, value)


def _ark_anthropic_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api/v3"):
        normalized = normalized[: -len("/api/v3")]
    if normalized.endswith("/api/compatible"):
        return normalized
    return f"{normalized}/api/compatible"


def _deepseek_anthropic_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    if normalized.endswith("/anthropic"):
        return normalized
    return f"{normalized}/anthropic"


__all__ = [
    "BaseUrlTransform",
    "CallMethodDefinition",
    "ClientCompatibility",
    "ProviderProbeBackend",
    "apply_call_method_base_url",
    "call_method_auth_token_env",
    "call_method_client_compatibility",
    "call_method_definition",
    "call_method_ids_for_client",
    "official_call_method_ids",
    "provider_probe_backend_for_method",
]
