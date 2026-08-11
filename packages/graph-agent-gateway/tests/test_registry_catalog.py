from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from graph_agent_gateway.registry import (
    CapabilityValue,
    EndpointCandidate,
    EvidenceRecord,
    ProviderImportDraft,
    RouteCandidate,
)


def _draft() -> ProviderImportDraft:
    return ProviderImportDraft(
        draft_id="draft-1",
        source={"url": "https://provider.example/docs"},
        status="pending",
        endpoint_candidates={
            "openai-direct": EndpointCandidate(
                endpoint_id="openai-direct",
                display_name="OpenAI Direct",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
            )
        },
        route_candidates={
            "openai-direct:gpt-5": RouteCandidate(
                endpoint_id="openai-direct",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
            )
        },
    )


def test_gateway_import_draft_store_round_trips_and_appends_evidence(tmp_path: Path) -> None:
    from graph_agent_gateway.registry import ProbeCatalogStore

    store = ProbeCatalogStore(tmp_path / "import_drafts.json")
    draft = store.save_draft(_draft())
    evidence = EvidenceRecord(
        evidence_id="evidence-1",
        evidence_type="probe",
        trust_state="probe-failed",
        endpoint_id="openai-direct",
        route_id="openai-direct:gpt-5",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        probe_status="error",
        reason="provider rejected the request",
        scope={"endpoint_id": "openai-direct", "route_id": "openai-direct:gpt-5"},
    )

    updated = store.append_evidence_record(evidence)

    assert store.load_draft(draft.draft_id).draft_id == "draft-1"
    assert updated.evidence_records[0].evidence_id == "evidence-1"
    assert store.load_evidence_library().evidence_records[0].reason == "provider rejected the request"


def test_gateway_materializes_import_draft_candidates_with_canonical_runtime_facts() -> None:
    from graph_agent_gateway.registry import materialize_probe_catalog_candidates

    draft = _draft().model_copy(
        update={
            "endpoint_candidates": {
                "openai-direct": _draft()
                .endpoint_candidates["openai-direct"]
                .model_copy(
                    update={
                        "protocol": "anthropic_compatible",
                        "base_url": "https://llm.wavespeed.ai/v1/",
                    }
                )
            }
        }
    )

    materialized = materialize_probe_catalog_candidates(draft)

    assert materialized.provider_endpoints["openai-direct"].base_url == "https://llm.wavespeed.ai"
    assert materialized.provider_routes["openai-direct:gpt-5"].status == "unverified_manual"
    assert materialized.endpoint_display_names["openai-direct"] == "OpenAI Direct"


def test_gateway_materialization_rejects_routes_with_missing_endpoint_candidates() -> None:
    from graph_agent_gateway.registry import materialize_probe_catalog_candidates

    draft = _draft().model_copy(
        update={
            "endpoint_candidates": {},
            "route_candidates": {
                "missing-endpoint:gpt-5": RouteCandidate(
                    endpoint_id="missing-endpoint",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                )
            },
        }
    )

    with pytest.raises(ValueError, match="missing endpoint"):
        materialize_probe_catalog_candidates(draft)


def test_gateway_materialization_preserves_secret_display_names_capabilities_and_metadata() -> None:
    from graph_agent_gateway.registry import materialize_probe_catalog_candidates

    draft = _draft().model_copy(
        update={
            "endpoint_candidates": {
                "openai-direct": _draft()
                .endpoint_candidates["openai-direct"]
                .model_copy(update={"metadata": {"region": "us-west"}})
            },
            "route_candidates": {
                "openai-direct:gpt-5": _draft()
                .route_candidates["openai-direct:gpt-5"]
                .model_copy(
                    update={
                        "capabilities": {
                            "max_output_tokens": CapabilityValue(value={"max": 128000}, source="agent_draft")
                        },
                        "metadata": {"family": "gpt"},
                    }
                )
            },
        }
    )

    materialized = materialize_probe_catalog_candidates(draft)

    endpoint = materialized.provider_endpoints["openai-direct"]
    route = materialized.provider_routes["openai-direct:gpt-5"]
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "secret"
    assert endpoint.metadata == {"region": "us-west"}
    assert materialized.endpoint_display_names["openai-direct"] == "OpenAI Direct"
    assert route.capabilities["max_output_tokens"].value == {"max": 128000}
    assert route.metadata == {"family": "gpt"}
    assert materialized.route_display_names["openai-direct:gpt-5"] == "GPT-5"


def test_import_draft_store_uses_shared_path_lock_for_concurrent_append(tmp_path: Path) -> None:
    from graph_agent_gateway.registry import ProbeCatalogStore

    path = tmp_path / "import_drafts.json"
    store_a = ProbeCatalogStore(path)
    store_b = ProbeCatalogStore(path)
    first_save_started = threading.Event()
    allow_first_save = threading.Event()
    original_save_all = store_a.save_all

    def delayed_save_all(drafts: dict[str, ProviderImportDraft]) -> None:
        first_save_started.set()
        assert allow_first_save.wait(timeout=2)
        original_save_all(drafts)

    store_a.save_all = delayed_save_all  # type: ignore[method-assign]

    first = EvidenceRecord(
        evidence_id="evidence-a",
        evidence_type="probe",
        trust_state="probe-verified",
        endpoint_id="openai-direct",
        route_id="openai-direct:gpt-5",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        probe_status="ok",
    )
    second = first.model_copy(update={"evidence_id": "evidence-b"})

    thread_a = threading.Thread(target=lambda: store_a.append_evidence_record(first))
    thread_b = threading.Thread(target=lambda: store_b.append_evidence_record(second))

    thread_a.start()
    assert first_save_started.wait(timeout=2)
    thread_b.start()
    time.sleep(0.05)
    allow_first_save.set()
    thread_a.join(timeout=2)
    thread_b.join(timeout=2)

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    evidence_ids = [record.evidence_id for record in store_a.load_evidence_library().evidence_records]
    assert evidence_ids == ["evidence-a", "evidence-b"]


def test_gateway_merges_remote_evidence_library_with_dedupe_and_route_metadata() -> None:
    from graph_agent_gateway.registry import merge_evidence_library, new_evidence_library

    local_route = RouteCandidate(
        endpoint_id="openai-direct",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        display_name="GPT-5",
        capabilities={"context": CapabilityValue(value={"max": 128000}, source="manual")},
        metadata={"local": True, "staleness": "old"},
    )
    remote_route = local_route.model_copy(
        update={
            "capabilities": {"thinking": CapabilityValue(value=True, source="probed_verified")},
            "metadata": {"remote": True, "staleness": "fresh"},
        }
    )
    duplicate = EvidenceRecord(
        evidence_id="evidence-same",
        evidence_type="probe",
        trust_state="probe-verified",
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        probe_status="ok",
    )
    fresh = duplicate.model_copy(update={"evidence_id": "evidence-new"})
    local = new_evidence_library("library").model_copy(
        update={
            "route_candidates": {"openai-direct:gpt-5": local_route},
            "evidence_records": [duplicate],
        }
    )
    remote = new_evidence_library("library").model_copy(
        update={
            "route_candidates": {"openai-direct:gpt-5": remote_route},
            "evidence_records": [duplicate, fresh],
        }
    )

    merged = merge_evidence_library(local, remote)

    route = merged.route_candidates["openai-direct:gpt-5"]
    assert set(route.capabilities) == {"context", "thinking"}
    assert route.metadata == {"local": True, "staleness": "fresh", "remote": True}
    assert [record.evidence_id for record in merged.evidence_records] == ["evidence-same", "evidence-new"]
