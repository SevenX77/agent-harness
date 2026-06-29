"""Phase 2a R5: wire ``probe_result`` <-> internal ``probe`` round-trip.

The community catalog speaks ``probe_result`` on the wire; the gateway's internal
evidence type is ``probe``. Ingestion maps the wire type back, marks community
provenance (so it is never confused with locally verified evidence), tolerates
unknown forward-compat fields, and fails closed on unexpected types.
"""

from __future__ import annotations

import pytest
from app.services.community_catalog import (
    COMMUNITY_PROVENANCE,
    build_upload_record,
    from_wire_evidence_type,
    parse_catalog_evidence,
    to_wire_evidence_type,
)

from tests.helpers_community_catalog import probe_record  # type: ignore[import-not-found]


def _wire_record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "evidence_id": "catalog-evidence-1",
        "evidence_type": "probe_result",
        "trust_state": "probe-verified",
        "provider_id": "deepseek",
        "provider_model_id": "deepseek-chat",
        "capability_family": "chat",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "observed_at": "2026-06-26T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_to_wire_evidence_type_maps_probe_to_probe_result() -> None:
    assert to_wire_evidence_type("probe") == "probe_result"


def test_from_wire_evidence_type_maps_probe_result_to_probe() -> None:
    assert from_wire_evidence_type("probe_result") == "probe"


def test_from_wire_evidence_type_rejects_unknown_type() -> None:
    # The probe catalog only ships probe_result; anything else fails closed.
    with pytest.raises(ValueError):
        from_wire_evidence_type("agent_note")


def test_parse_catalog_evidence_produces_internal_probe_type() -> None:
    record = parse_catalog_evidence(_wire_record())
    assert record.evidence_type == "probe"


def test_parse_catalog_evidence_marks_community_provenance() -> None:
    record = parse_catalog_evidence(_wire_record())
    assert record.metadata.get("provenance") == COMMUNITY_PROVENANCE


def test_parse_catalog_evidence_preserves_safe_capability_fields() -> None:
    record = parse_catalog_evidence(_wire_record())
    assert record.provider_id == "deepseek"
    assert record.provider_model_id == "deepseek-chat"
    assert record.capability_family == "chat"
    assert record.input_modalities == ["text"]


def test_parse_catalog_evidence_tolerates_unknown_wire_fields() -> None:
    # Forward-compat: a future wire field must be dropped, not crash ingestion.
    record = parse_catalog_evidence(_wire_record(future_field="ignore-me"))
    assert record.evidence_type == "probe"


def test_parse_catalog_evidence_requires_evidence_id() -> None:
    wire = _wire_record()
    del wire["evidence_id"]
    with pytest.raises(ValueError):
        parse_catalog_evidence(wire)


def test_parse_catalog_evidence_rejects_non_probe_result() -> None:
    with pytest.raises(ValueError):
        parse_catalog_evidence(_wire_record(evidence_type="provider_docs"))


def test_round_trip_upload_then_ingest_preserves_safe_fields() -> None:
    original = probe_record(
        provider_id="openai",
        provider_model_id="gpt-4o",
        capability_family="chat",
    )
    upload = build_upload_record(original, base_url="https://api.openai.com/v1")
    wire = upload.model_dump(mode="json")
    wire["evidence_id"] = "catalog-assigned-id"
    ingested = parse_catalog_evidence(wire)
    assert ingested.evidence_type == "probe"
    assert ingested.provider_id == "openai"
    assert ingested.provider_model_id == "gpt-4o"
    assert ingested.capability_family == "chat"
    assert ingested.metadata["provenance"] == COMMUNITY_PROVENANCE
    # Phase 5: the published endpoint identity lands on the FORMAL field (so it feeds
    # content_hash + host matching), not in metadata.
    assert ingested.normalized_public_base_url == "https://api.openai.com/v1"
