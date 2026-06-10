"""Endpoint standardization helpers for raw provider credentials."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from graph_agent_gateway.registry.base_url import canonicalize_base_url
from graph_agent_gateway.registry.schema import (
    EndpointCandidate,
    ProbeResult,
    Protocol,
    ProviderKind,
)

DEFAULT_PROTOCOL_PROBES: tuple[Protocol, ...] = (
    "openai_compatible",
    "anthropic_compatible",
    "google_genai",
    "ark_runtime",
)

_PROTOCOL_ID_SUFFIX: dict[Protocol, str] = {
    "openai_compatible": "openai",
    "anthropic_compatible": "anthropic",
    "google_genai": "google",
    "ark_runtime": "ark",
}

_OFFICIAL_LEGACY_ENDPOINT_IDS = {
    "api.anthropic.com": "anthropic-official",
    "api.openai.com": "openai-official",
    "api.deepseek.com": "deepseek-official",
    "generativelanguage.googleapis.com": "gemini-official",
}

ProtocolProbe = Callable[[str, Protocol, str | None], "ProtocolProbeResult"]


class RawProviderEndpointInput(BaseModel):
    """Raw provider-card input before URL/protocol endpoint splitting."""

    model_config = ConfigDict(extra="forbid")

    display_name: str
    urls: list[str]
    provider_slug: str | None = None
    api_key: SecretStr | str | None = None
    credential_ref: str | None = None
    provider_kind: ProviderKind = "third_party"
    rate_limit_bucket: str | None = None
    timeout_seconds: int = 120
    trust_env: bool = False
    proxy_env: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProtocolProbeResult(BaseModel):
    """Result of trying one protocol against one raw base URL."""

    model_config = ConfigDict(extra="forbid")

    protocol: Protocol
    ok: bool
    message: str | None = None
    observed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EndpointStandardizationResult(BaseModel):
    """Standard endpoint candidates plus probe evidence."""

    model_config = ConfigDict(extra="forbid")

    endpoint_candidates: dict[str, EndpointCandidate] = Field(default_factory=dict)
    probe_results: dict[str, ProbeResult] = Field(default_factory=dict)


class _DetectedEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_url: str
    canonical_base_url: str
    protocol: Protocol
    probe: ProtocolProbeResult


def standardize_endpoint_candidates(
    raw: RawProviderEndpointInput,
    *,
    probe: ProtocolProbe,
    protocols: Sequence[Protocol] = DEFAULT_PROTOCOL_PROBES,
    reserved_endpoint_ids: Iterable[str] = (),
) -> EndpointStandardizationResult:
    """Split raw provider input into protocol-specific endpoint candidates."""

    provider_slug = _endpoint_slug(raw.provider_slug or raw.display_name or _fallback_host(raw.urls))
    raw_urls = _normalized_urls(raw.urls)
    api_key = _secret_value(raw.api_key)
    detected: list[_DetectedEndpoint] = []
    probe_results: dict[str, ProbeResult] = {}

    for raw_url in raw_urls:
        for protocol in protocols:
            probe_result = probe(raw_url, protocol, api_key)
            probe_key = f"{raw_url}#{protocol}"
            probe_results[probe_key] = ProbeResult(
                target_type="endpoint",
                status="success" if probe_result.ok else "failed",
                observed_at=probe_result.observed_at,
                error=None if probe_result.ok else {"message": probe_result.message or ""},
                capabilities={},
            )
            if not probe_result.ok:
                continue
            detected.append(
                _DetectedEndpoint(
                    raw_url=raw_url,
                    canonical_base_url=canonicalize_base_url(raw_url, protocol),
                    protocol=protocol,
                    probe=probe_result,
                )
            )

    endpoint_candidates: dict[str, EndpointCandidate] = {}
    assigned_ids = _assign_endpoint_ids(
        provider_slug,
        detected,
        reserved_endpoint_ids=set(reserved_endpoint_ids),
    )
    for endpoint_id, item in sorted(assigned_ids.items()):
        endpoint_candidates[endpoint_id] = EndpointCandidate(
            endpoint_id=endpoint_id,
            display_name=_candidate_display_name(raw.display_name, item.protocol),
            protocol=item.protocol,
            base_url=item.canonical_base_url,
            credential_ref=raw.credential_ref,
            api_key=_secret_for_endpoint(raw.api_key),
            status="verified",
            last_test_at=item.probe.observed_at,
            last_test_message=item.probe.message,
            provider_kind=raw.provider_kind,
            rate_limit_bucket=raw.rate_limit_bucket,
            timeout_seconds=raw.timeout_seconds,
            trust_env=raw.trust_env,
            proxy_env=raw.proxy_env,
            metadata={
                **raw.metadata,
                **item.probe.metadata,
                "canonical_source": {
                    "provider_slug": provider_slug,
                    "raw_url": item.raw_url,
                    "protocol": item.protocol,
                },
            },
        )

    return EndpointStandardizationResult(
        endpoint_candidates=endpoint_candidates,
        probe_results=probe_results,
    )


def canonical_endpoint_id_base(provider_slug: str, protocol: Protocol) -> str:
    """Return the unsuffixed endpoint id base for a provider/protocol pair."""

    return f"{_endpoint_slug(provider_slug)}-{_PROTOCOL_ID_SUFFIX[protocol]}"


def legacy_v3_endpoint_id(provider: dict[str, Any]) -> str:
    """Return the historical v3->v4 endpoint id for one legacy provider."""

    raw = str(provider.get("id") or provider.get("code") or "").strip()
    name = str(provider.get("name") or "").lower()
    base_url = str(provider.get("base_url") or "").strip()
    base_host = _url_hostname(base_url)
    base_path = _url_path(base_url)
    if base_host in _OFFICIAL_LEGACY_ENDPOINT_IDS:
        return _OFFICIAL_LEGACY_ENDPOINT_IDS[base_host]
    if _host_matches(base_host, "volces.com"):
        return "ark-official"
    if product_endpoint_id := _legacy_product_endpoint_id(base_host, base_path, name):
        return product_endpoint_id
    return raw


def _legacy_product_endpoint_id(base_host: str, base_path: str, name: str) -> str | None:
    if _host_matches(base_host, "openrouter.ai") or "openrouter" in name:
        return "openrouter-prod"
    if "wavespeed" in base_host or "wavespeed" in name:
        return "wavespeed-prod"
    if not _host_matches(base_host, "qnaigc.com"):
        return None
    if "anthropic" in base_path or "anthropic" in name:
        return "qiniu-anthropic"
    return "qiniu-openai"


def _assign_endpoint_ids(
    provider_slug: str,
    detected: list[_DetectedEndpoint],
    *,
    reserved_endpoint_ids: set[str],
) -> dict[str, _DetectedEndpoint]:
    assigned: dict[str, _DetectedEndpoint] = {}
    by_base_id: dict[str, list[_DetectedEndpoint]] = {}
    for item in detected:
        by_base_id.setdefault(canonical_endpoint_id_base(provider_slug, item.protocol), []).append(item)

    used = set(reserved_endpoint_ids)
    for base_id, items in sorted(by_base_id.items()):
        for item in sorted(items, key=lambda value: (value.canonical_base_url, value.raw_url)):
            endpoint_id = _next_endpoint_id(base_id, used)
            used.add(endpoint_id)
            assigned[endpoint_id] = item
    return assigned


def _next_endpoint_id(base_id: str, used: set[str]) -> str:
    if base_id not in used:
        return base_id
    suffix = 2
    while f"{base_id}-{suffix}" in used:
        suffix += 1
    return f"{base_id}-{suffix}"


def _normalized_urls(urls: Sequence[str]) -> list[str]:
    normalized = {
        value.strip().rstrip("/")
        for value in urls
        if value.strip().rstrip("/")
    }
    return sorted(normalized)


def _endpoint_slug(value: str) -> str:
    slug = value.strip().lower().replace("_", "-")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "endpoint"


def _candidate_display_name(display_name: str, protocol: Protocol) -> str:
    return f"{display_name} ({_PROTOCOL_ID_SUFFIX[protocol]})"


def _fallback_host(urls: Sequence[str]) -> str:
    for url in urls:
        host = _url_hostname(url)
        if host:
            return host.split(".")[0]
    return "endpoint"


def _secret_value(secret: SecretStr | str | None) -> str | None:
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return secret


def _secret_for_endpoint(secret: SecretStr | str | None) -> SecretStr | None:
    if isinstance(secret, SecretStr):
        return secret
    if secret is None:
        return None
    return SecretStr(secret)


def _url_hostname(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    return (parsed.hostname or "").lower().rstrip(".")


def _url_path(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    return parsed.path.lower()


def _host_matches(hostname: str, domain: str) -> bool:
    normalized_domain = domain.lower().rstrip(".")
    return hostname == normalized_domain or hostname.endswith(f".{normalized_domain}")


__all__ = [
    "EndpointStandardizationResult",
    "ProtocolProbe",
    "ProtocolProbeResult",
    "RawProviderEndpointInput",
    "canonical_endpoint_id_base",
    "legacy_v3_endpoint_id",
    "standardize_endpoint_candidates",
]
