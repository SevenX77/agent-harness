"""Stable, opaque evidence IDs for credential ``route.evidence`` records.

A tiny neutral helper extracted from the retired probe-catalog storage layer
(``llm_import_drafts``): minting an evidence ID has nothing to do with where the
evidence is stored, and evidence now lives in credentials ``route.evidence`` (SSOT).
Keeping it here lets the runtime mint IDs without importing the dead catalog layer.
"""

from __future__ import annotations

import uuid


def new_evidence_id(prefix: str = "evidence") -> str:
    """Return a compact unique evidence ID, e.g. ``probe-<hex>``."""
    return f"{prefix}-{uuid.uuid4().hex}"


__all__ = ["new_evidence_id"]
