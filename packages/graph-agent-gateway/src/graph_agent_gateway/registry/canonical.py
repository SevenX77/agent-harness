"""Conservative model canonicalization."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from graph_agent_gateway.registry.route_identity import route_slug, strip_transport_prefix

CanonicalConfidence = Literal["transport_normalized", "explicit_alias", "orphan"]


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
        canonical = _slug(alias)
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


def _slug(value: str) -> str:
    slug = value.strip().lower().replace("/", ".").replace("_", "-")
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown"
