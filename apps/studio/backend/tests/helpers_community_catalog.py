"""Shared fixtures for community probe catalog tests."""

from __future__ import annotations

from app.core.adapters.gateway import EvidenceRecord


def probe_record(**overrides: object) -> EvidenceRecord:
    """Return a minimal probe-verified probe evidence record for tests."""
    base: dict[str, object] = {
        "evidence_id": "evidence-1",
        "evidence_type": "probe",
        "trust_state": "probe-verified",
        "provider_id": "deepseek",
        "provider_model_id": "deepseek-chat",
        "observed_at": "2026-06-26T00:00:00+00:00",
    }
    base.update(overrides)
    return EvidenceRecord.model_validate(base)
