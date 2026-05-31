"""Conservative model canonicalization."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    del endpoint_id
    aliases = explicit_aliases or {}
    if provider_model_id in aliases:
        canonical = _slug(aliases[provider_model_id])
        return CanonicalModel(
            canonical_id=canonical,
            confidence="explicit_alias",
        )

    if provider_model_id.startswith("anthropic/"):
        canonical = _slug(provider_model_id.removeprefix("anthropic/"))
        return CanonicalModel(
            canonical_id=canonical,
            confidence="transport_normalized",
        )

    canonical = _slug(provider_model_id)
    return CanonicalModel(
        canonical_id=canonical,
        confidence="orphan",
    )


def _slug(value: str) -> str:
    slug = value.strip().lower().replace("/", ".").replace("_", "-")
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown"
