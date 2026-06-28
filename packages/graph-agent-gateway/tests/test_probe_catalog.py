from __future__ import annotations

from pathlib import Path

from graph_agent_gateway.registry.schema import EvidenceRecord


def test_probe_catalog_store_is_canonical_public_api(tmp_path: Path) -> None:
    from graph_agent_gateway.probe_catalog import ProbeCatalogStore

    store = ProbeCatalogStore(tmp_path / "llm_probe_catalog.json")
    evidence = EvidenceRecord(
        evidence_id="evidence-1",
        evidence_type="probe",
        trust_state="probe-verified",
        endpoint_id="openai-official",
        route_id="openai-official:gpt-5",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        probe_status="ok",
        scope={"endpoint_id": "openai-official", "route_id": "openai-official:gpt-5"},
    )

    updated = store.append_evidence_record(evidence)

    assert updated.draft_id == "studio-evidence-library"
    assert store.load_evidence_library().evidence_records[0].evidence_id == "evidence-1"


def test_probe_catalog_store_is_exported_from_gateway_package() -> None:
    from graph_agent_gateway import ProbeCatalogStore
    from graph_agent_gateway.probe_catalog import ProbeCatalogStore as CanonicalProbeCatalogStore

    assert ProbeCatalogStore is CanonicalProbeCatalogStore


def test_probe_catalog_candidate_materializer_uses_canonical_public_names() -> None:
    from graph_agent_gateway import (
        MaterializedProbeCatalogCandidates,
        materialize_probe_catalog_candidates,
    )
    from graph_agent_gateway.probe_catalog import (
        MaterializedProbeCatalogCandidates as CatalogCandidates,
    )
    from graph_agent_gateway.probe_catalog import (
        materialize_probe_catalog_candidates as catalog_materializer,
    )

    assert MaterializedProbeCatalogCandidates is CatalogCandidates
    assert materialize_probe_catalog_candidates is catalog_materializer


def test_canonical_probe_catalog_facades_do_not_advertise_legacy_draft_names() -> None:
    import graph_agent_gateway as gateway
    import graph_agent_gateway.probe_catalog as catalog

    legacy_public_names = {
        "ImportDraftStore",
        "MaterializedImportDraftCandidates",
        "materialize_import_draft_candidates",
    }

    assert set(gateway.__all__).isdisjoint(legacy_public_names)
    assert set(catalog.__all__).isdisjoint(
        {"MaterializedImportDraftCandidates", "materialize_import_draft_candidates"}
    )
