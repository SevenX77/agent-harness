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


def _clean_input(val: Any) -> Any:
    """Recursively coerce Pydantic models and structures into JSON-safe primitives."""
    if isinstance(val, dict):
        return {k: _clean_input(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple, set)):
        return [_clean_input(v) for v in val]
    elif hasattr(val, "model_dump") and callable(getattr(val, "model_dump")):
        return _clean_input(val.model_dump(mode="json"))
    elif hasattr(val, "dict") and callable(getattr(val, "dict")):
        return _clean_input(val.dict())
    return val


def input_hash(inputs: dict[str, Any]) -> str:
    """Compute a stable SHA256 hex signature from inputs dictionary, robust against key order and Pydantic models."""
    cleaned = _clean_input(inputs)
    canonical = json.dumps(
        cleaned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return _sha256_text(canonical)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["prompt_hash", "schema_hash", "input_hash"]
