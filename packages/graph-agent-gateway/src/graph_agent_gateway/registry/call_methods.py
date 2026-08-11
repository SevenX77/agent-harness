"""Gateway-owned runtime catalog for provider call methods."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Literal, cast
from urllib.parse import urlparse

from graph_agent_gateway.registry.base_url import canonicalize_base_url

ProviderProbeBackend = Literal["ark", "claude", "deepseek", "gemini", "openai"]
ClientCompatibility = Literal["supported", "incompatible", "unknown"]
BaseUrlTransform = Literal[
    "none",
    "anthropic_compatible",
    "ark_anthropic_compatible",
    "deepseek_anthropic",
]

_BACKENDS: frozenset[str] = frozenset({"ark", "claude", "deepseek", "gemini", "openai"})
_COMPAT_VALUES: frozenset[str] = frozenset({"supported", "incompatible", "unknown"})
_PROTOCOL_VALUES: frozenset[str] = frozenset(
    {"openai_compatible", "anthropic_compatible", "google_genai", "ark_runtime"}
)
_BASE_URL_TRANSFORMS: frozenset[str] = frozenset(
    {"none", "anthropic_compatible", "ark_anthropic_compatible", "deepseek_anthropic"}
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


@dataclass(frozen=True)
class EndpointCallMethodRule:
    host_suffix: str
    protocols: tuple[str, ...]
    method_ids: tuple[str, ...]


@dataclass(frozen=True)
class CallMethodCatalog:
    methods: dict[str, CallMethodDefinition]
    protocol_defaults: dict[str, tuple[str, ...]]
    host_overrides: tuple[EndpointCallMethodRule, ...]


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


def call_method_ids_for_endpoint(protocol: str | None, base_url: str | None) -> tuple[str, ...]:
    """Return endpoint-level method candidates from gateway catalog truth.

    A route profile is still the strongest method evidence. This function covers
    the pre-profile gap: endpoint protocol and known multi-protocol hosts tell a
    consumer which method should be tried before the route has verified profile
    rows. Callers still decide which client compatibility they require.
    """

    if not protocol:
        return ()
    catalog = _call_method_catalog()
    candidates: list[str] = list(catalog.protocol_defaults.get(str(protocol), ()))
    hostname = _url_hostname(base_url or "")
    if hostname:
        for rule in catalog.host_overrides:
            if str(protocol) in rule.protocols and _host_matches(hostname, rule.host_suffix):
                candidates.extend(rule.method_ids)
    return _ordered_unique(candidates)


def call_method_client_compatibility(method_id: str | None, client_id: str) -> ClientCompatibility:
    if not method_id:
        return "unknown"
    definition = call_method_definition(method_id)
    if definition is None:
        return "unknown"
    return definition.client_compatibility.get(client_id, "unknown")


def preferred_call_method_for_endpoint(protocol: str | None, base_url: str | None) -> str:
    """The call method an endpoint speaks, before any route has proved one.

    `call_method_ids_for_endpoint` is preference-ordered, so the first candidate
    is the one a call to this endpoint would reach for. An endpoint whose
    protocol has no registered method cannot be called at all, which is a
    catalog gap and not something to paper over with a default.
    """

    candidates = call_method_ids_for_endpoint(protocol, base_url)
    if not candidates:
        raise ValueError(f"No call method is registered for protocol: {protocol!r}")
    return candidates[0]


def provider_backend_for_method(method_id: str) -> ProviderProbeBackend:
    """Which provider implementation stands behind a call method."""

    definition = call_method_definition(method_id)
    if definition is None:
        raise ValueError(f"Unknown call method: {method_id}")
    return definition.provider_backend


def call_method_is_officially_probeable(method_id: str) -> bool:
    """Whether the official-method probe offers this method.

    Separate from whether the method can be sent at all: every method in the
    catalog has a dialect, and this flag only says which ones the "test this
    model against its official API" surface lists.
    """

    definition = call_method_definition(method_id)
    return definition is not None and definition.official_probe


def apply_call_method_base_url(method_id: str | None, base_url: str) -> str:
    definition = call_method_definition(method_id or "")
    transform = definition.base_url_transform if definition is not None else "none"
    if transform == "anthropic_compatible":
        return canonicalize_base_url(base_url, "anthropic_compatible")
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
    return _call_method_catalog().methods


@lru_cache(maxsize=1)
def _call_method_catalog() -> CallMethodCatalog:
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
    protocol_defaults, host_overrides = _endpoint_method_candidates_from_raw(raw, table)
    return CallMethodCatalog(
        methods=table,
        protocol_defaults=protocol_defaults,
        host_overrides=host_overrides,
    )


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


def _endpoint_method_candidates_from_raw(
    raw: dict[str, Any],
    table: dict[str, CallMethodDefinition],
) -> tuple[dict[str, tuple[str, ...]], tuple[EndpointCallMethodRule, ...]]:
    candidates_raw = raw.get("endpoint_method_candidates", {})
    if not isinstance(candidates_raw, dict):
        raise ValueError("endpoint_method_candidates must be an object")
    protocol_raw = candidates_raw.get("protocol_defaults", {})
    if not isinstance(protocol_raw, dict):
        raise ValueError("endpoint_method_candidates.protocol_defaults must be an object")
    protocol_defaults: dict[str, tuple[str, ...]] = {}
    for protocol, methods_raw in protocol_raw.items():
        if protocol not in _PROTOCOL_VALUES:
            raise ValueError(f"endpoint method candidates contain unknown protocol {protocol}")
        protocol_defaults[str(protocol)] = _method_ids(methods_raw, table, f"protocol {protocol}")

    rules_raw = candidates_raw.get("host_overrides", [])
    if not isinstance(rules_raw, list):
        raise ValueError("endpoint_method_candidates.host_overrides must be a list")
    host_overrides = tuple(_endpoint_rule_from_raw(item, table) for item in rules_raw)
    return protocol_defaults, host_overrides


def _endpoint_rule_from_raw(
    raw: object,
    table: dict[str, CallMethodDefinition],
) -> EndpointCallMethodRule:
    if not isinstance(raw, dict):
        raise ValueError("endpoint host override must be an object")
    host_suffix = _required_str(raw, "host_suffix").lower().lstrip(".")
    protocols_raw = raw.get("protocols")
    if not isinstance(protocols_raw, list) or not protocols_raw:
        raise ValueError(f"{host_suffix}: protocols must be a non-empty list")
    protocols: list[str] = []
    for protocol in protocols_raw:
        if not isinstance(protocol, str) or protocol not in _PROTOCOL_VALUES:
            raise ValueError(f"{host_suffix}: unknown protocol {protocol}")
        protocols.append(protocol)
    return EndpointCallMethodRule(
        host_suffix=host_suffix,
        protocols=tuple(protocols),
        method_ids=_method_ids(raw.get("method_ids"), table, f"host {host_suffix}"),
    )


def _method_ids(
    raw: object,
    table: dict[str, CallMethodDefinition],
    owner: str,
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{owner}: method_ids must be a list")
    method_ids: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{owner}: method id must be a non-empty string")
        if item not in table:
            raise ValueError(f"{owner}: unknown method id {item}")
        method_ids.append(item)
    return tuple(_ordered_unique(method_ids))


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _url_hostname(base_url: str) -> str:
    try:
        return (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return ""


def _host_matches(hostname: str, suffix: str) -> bool:
    return hostname == suffix or hostname.endswith(f".{suffix}")


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
    "call_method_ids_for_endpoint",
    "call_method_ids_for_client",
    "official_call_method_ids",
    "call_method_is_officially_probeable",
    "preferred_call_method_for_endpoint",
    "provider_backend_for_method",
]
