"""Hash helpers for Predict V2 Golden Case freshness checks."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def prompt_hash(text: str) -> str:
    """Return a stable hash for prompt text after whitespace normalization."""
    if not isinstance(text, str):
        raise TypeError("prompt_hash expects a string")
    normalized = _WHITESPACE_RE.sub(" ", text).strip()
    return _sha256_text(normalized)


def schema_hash(schema: dict[str, Any]) -> str:
    """Return a stable hash for a JSON schema using canonical key ordering."""
    canonical = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return _sha256_text(canonical)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["prompt_hash", "schema_hash"]
