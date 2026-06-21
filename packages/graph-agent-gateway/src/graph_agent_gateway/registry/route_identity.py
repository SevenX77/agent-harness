"""Stable endpoint and route identity helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

from graph_agent_gateway.registry.base_url import canonicalize_base_url
from graph_agent_gateway.registry.schema import Protocol

_PROTOCOL_ID_SUFFIX: dict[Protocol, str] = {
    "openai_compatible": "openai",
    "anthropic_compatible": "anthropic",
    "google_genai": "google",
    "ark_runtime": "ark",
}


def stable_endpoint_id(*, protocol: Protocol, base_url: str) -> str:
    """Return the persisted endpoint id for a protocol/base-url pair."""

    canonical_base_url = canonicalize_base_url(base_url, protocol)
    identity = f"{protocol}|{canonical_base_url}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    return f"{_base_url_slug(canonical_base_url)}-{_PROTOCOL_ID_SUFFIX[protocol]}-{digest}"


def stable_route_id(
    *,
    protocol: Protocol,
    base_url: str,
    provider_model_id: str,
) -> str:
    """Return the persisted route id for one physical model route."""

    return f"{stable_endpoint_id(protocol=protocol, base_url=base_url)}:{route_slug(provider_model_id)}"


def route_slug(provider_model_id: str) -> str:
    """Return the route-safe slug for a provider model id."""

    slug = provider_model_id.strip().lower().replace("/", ".").replace("_", "-")
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    slug = re.sub(r"^(claude-(?:sonnet|opus|haiku)-\d+)-(\d+)$", r"\1.\2", slug)
    return slug or "unknown"


def _base_url_slug(base_url: str) -> str:
    parsed = urlsplit(base_url)
    host = parsed.netloc.lower().strip()
    path = parsed.path.strip("/")
    raw = "-".join(part for part in (host, path) if part)
    slug = raw.replace(".", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "endpoint"


__all__ = ["route_slug", "stable_endpoint_id", "stable_route_id"]
