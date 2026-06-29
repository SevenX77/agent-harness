"""Red tests for EvidenceRecord content_hash — Studio LLM credentials/catalog SSOT.

T1.1 (Phase 1): pins the deterministic content-hash contract (requirements R2.1)
and the new FORMAL ``normalized_public_base_url`` field (problem 3) BEFORE the
gateway schema implements them. These fail until T1.2 adds the two fields plus
``compute_evidence_content_hash`` to ``graph_agent_gateway.registry.schema``.
"""

from __future__ import annotations

import pytest
from graph_agent_gateway.registry.schema import (
    EvidenceRecord,
    compute_evidence_content_hash,
)


def _evidence(**overrides: object) -> EvidenceRecord:
    """Build a probe-verified evidence record with sane semantic defaults."""
    base: dict[str, object] = {
        "evidence_id": "evidence-local-1",
        "evidence_type": "probe",
        "trust_state": "probe-verified",
        "normalized_public_base_url": "https://api.example.com/v1",
        "provider_model_id": "gpt-5",
        "model_id": "gpt-5",
        "method_id": "chat_completions",
        "request_mapper_id": "openai_chat",
        "probe_status": "ok",
        "capability_family": "language",
        "observed_at": "2026-06-01T00:00:00Z",
    }
    base.update(overrides)
    return EvidenceRecord(**base)  # type: ignore[arg-type]


def test_same_semantics_differ_only_timestamp_yield_same_hash() -> None:
    # R2.1-AC1: identical semantics, only evidence_id + observed_at differ.
    a = _evidence(evidence_id="evidence-1", observed_at="2026-06-01T00:00:00Z")
    b = _evidence(evidence_id="evidence-2", observed_at="2026-06-29T12:34:56Z")
    assert compute_evidence_content_hash(a) == compute_evidence_content_hash(b)


def test_hash_has_sha256_prefix_and_is_deterministic() -> None:
    rec = _evidence()
    first = compute_evidence_content_hash(rec)
    second = compute_evidence_content_hash(rec)
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalized_public_base_url", "https://api.other.com/v1"),
        ("provider_model_id", "gpt-4o"),
        ("model_id", "gpt-4o-mini"),
        ("method_id", "responses"),
        ("request_mapper_id", "anthropic_messages"),
        ("probe_status", "invalid_model"),
        ("trust_state", "probe-failed"),
        ("evidence_type", "model_list_observation"),
        ("capability_family", "vision"),
    ],
)
def test_changing_any_semantic_field_changes_hash(field: str, value: str) -> None:
    # R2.1-AC2: any semantic field change must change the hash.
    base_hash = compute_evidence_content_hash(_evidence())
    changed_hash = compute_evidence_content_hash(_evidence(**{field: value}))
    assert base_hash != changed_hash


def test_local_and_remote_align_on_formal_field_metadata_ignored() -> None:
    # problem 3: endpoint identity is a FORMAL field, so a locally-built record
    # and a remote ``parse_catalog_evidence`` record carrying the same public
    # base URL hash identically — even though evidence_id / observed_at / metadata
    # differ. metadata MUST NOT feed the hash.
    local = _evidence(evidence_id="evidence-local", metadata={})
    remote = _evidence(
        evidence_id="evidence-remote",
        observed_at="2026-06-29T00:00:00Z",
        metadata={"provenance": "community", "route_key": "fp:gpt-5:chat_completions"},
    )
    assert compute_evidence_content_hash(local) == compute_evidence_content_hash(remote)


def test_new_fields_default_none_and_roundtrip_backward_compatible() -> None:
    # Old data (no content_hash / normalized_public_base_url) must still validate.
    rec = EvidenceRecord(
        evidence_id="evidence-x",
        evidence_type="probe",
        trust_state="probe-verified",
    )
    assert rec.content_hash is None
    assert rec.normalized_public_base_url is None
    restored = EvidenceRecord.model_validate_json(rec.model_dump_json())
    assert restored.content_hash is None
    assert restored.normalized_public_base_url is None


def test_content_hash_field_is_assignable_for_merge_writeback() -> None:
    # merge_route_evidence (Phase 2) stamps the computed hash back onto the record.
    rec = _evidence()
    digest = compute_evidence_content_hash(rec)
    stamped = rec.model_copy(update={"content_hash": digest})
    assert stamped.content_hash == digest
