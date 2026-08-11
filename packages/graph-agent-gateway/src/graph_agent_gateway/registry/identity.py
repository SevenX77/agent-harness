"""A model's identity: the ids it is stored under, and the group it belongs to.

Both questions are answered from the same two strings — the endpoint's
(protocol, base_url) pair and the provider's model id — so they are answered in
one place. Splitting them once meant the grouping key and the route id suffix
were derived by two functions that had to agree byte for byte across a file
boundary; here that agreement is visible.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from graph_agent_gateway.registry.base_url import canonicalize_base_url
from graph_agent_gateway.registry.schema import Protocol

CanonicalConfidence = Literal["transport_normalized", "explicit_alias", "orphan"]

_PROTOCOL_ID_SUFFIX: dict[Protocol, str] = {
    "openai_compatible": "openai",
    "anthropic_compatible": "anthropic",
    "google_genai": "google",
    "ark_runtime": "ark",
}

# Vendor/transport routing prefixes that identify HOW a model is reached (via a
# proxy such as openrouter), NOT which model it is. Stripped from the grouping
# identity so the same model reached officially and via a proxy shares one
# canonical group (and thus one model_group with fallback routes). The raw
# ``provider_model_id`` used to actually call the provider is stored separately
# and never touched.
_TRANSPORT_PREFIXES: tuple[str, ...] = ("anthropic/",)


def strip_transport_prefix(provider_model_id: str) -> str:
    """Strip a known transport/vendor routing prefix from a provider model id.

    Only the exact known transport prefix is removed; the remaining model
    identity (including real variant suffixes like ``-fast``) is preserved.
    """

    value = provider_model_id.strip()
    lowered = value.lower()
    for prefix in _TRANSPORT_PREFIXES:
        if lowered.startswith(prefix):
            return value[len(prefix) :]
    return value


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

    slug = strip_transport_prefix(provider_model_id).lower().replace("/", ".").replace("_", "-")
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


class CanonicalModel(BaseModel):
    """Canonical grouping result."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    confidence: CanonicalConfidence


def canonicalize_model(
    *,
    endpoint_id: str,
    provider_model_id: str,
    explicit_aliases: dict[str, str] | None = None,
) -> CanonicalModel:
    """Map a provider model ID to a conservative execution grouping key."""
    aliases = explicit_aliases or {}
    alias = aliases.get(f"{endpoint_id}:{provider_model_id}") or aliases.get(provider_model_id)
    if alias:
        canonical = _alias_slug(alias)
        return CanonicalModel(
            canonical_id=canonical,
            confidence="explicit_alias",
        )

    # canonical_id MUST equal route_slug(provider_model_id): the copilot vocab
    # guard requires the route_id suffix (route_slug) to equal the group's
    # canonical_id. route_slug already strips the transport prefix; deriving
    # canonical from it keeps the two byte-identical. A stripped prefix means the
    # grouping was transport-normalized; otherwise it stands alone (orphan).
    confidence: CanonicalConfidence = (
        "transport_normalized"
        if strip_transport_prefix(provider_model_id) != provider_model_id.strip()
        else "orphan"
    )
    return CanonicalModel(
        canonical_id=route_slug(provider_model_id),
        confidence=confidence,
    )


def _alias_slug(value: str) -> str:
    """Slugify a hand-written alias.

    Unlike ``route_slug`` this keeps a transport prefix and applies no model
    naming rules: an alias is what someone wrote down, not a model id.
    """
    slug = value.strip().lower().replace("/", ".").replace("_", "-")
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown"


__all__ = [
    "CanonicalConfidence",
    "CanonicalModel",
    "canonicalize_model",
    "route_slug",
    "stable_endpoint_id",
    "stable_route_id",
    "strip_transport_prefix",
]
