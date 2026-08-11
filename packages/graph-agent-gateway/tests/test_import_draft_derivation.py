from __future__ import annotations

from graph_agent_gateway.registry import (
    CapabilityValue,
    EvidenceRecord,
    ProviderImportDraft,
    ProviderRoute,
    RouteCandidate,
    known_model_ids_for_endpoint,
    known_verified_capabilities,
    probe_priority,
    promotable_route_update,
)


def _library(*records: EvidenceRecord) -> ProviderImportDraft:
    return ProviderImportDraft(
        draft_id="studio-evidence-library",
        source={"kind": "studio_evidence_library"},
        status="pending",
        evidence_records=list(records),
    )


def test_known_verified_capabilities_only_uses_probe_verified_evidence() -> None:
    library = _library(
        EvidenceRecord(
            evidence_id="observed",
            evidence_type="model_list_observation",
            trust_state="provider-list-observed",
            endpoint_id="openai",
            route_id="openai:gpt-5",
            model_id="gpt-5",
            provider_model_id="gpt-5",
            candidate_capabilities={
                "tool_protocol": CapabilityValue(value=False, source="api_list")
            },
        ),
        EvidenceRecord(
            evidence_id="verified",
            evidence_type="probe",
            trust_state="probe-verified",
            endpoint_id="openai",
            route_id="openai:gpt-5",
            model_id="gpt-5",
            provider_model_id="gpt-5",
            candidate_capabilities={
                "tool_protocol": CapabilityValue(value=True, source="probed_verified")
            },
        ),
    )

    capabilities = known_verified_capabilities(library, "openai", "gpt-5")

    assert capabilities["tool_protocol"].value is True
    assert capabilities["tool_protocol"].source == "probed_verified"


def test_known_model_ids_for_endpoint_uses_draft_route_candidates_and_probe_evidence() -> None:
    library = _library(
        EvidenceRecord(
            evidence_id="verified",
            evidence_type="probe",
            trust_state="probe-verified",
            endpoint_id="openai",
            route_id="openai:gpt-5",
            model_id="gpt-5",
            provider_model_id="gpt-5",
        )
    )
    library = library.model_copy(
        update={
            "route_candidates": {
                "openai:gpt-4.1": RouteCandidate(
                    endpoint_id="openai",
                    route_slug="gpt-4.1",
                    provider_model_id="gpt-4.1",
                    canonical_id="gpt-4.1",
                    display_name="gpt-4.1",
                )
            }
        }
    )

    assert known_model_ids_for_endpoint(library, "openai") == ["gpt-4.1", "gpt-5"]


def test_probe_priority_skips_verified_and_keeps_failed_last() -> None:
    library = _library(
        EvidenceRecord(
            evidence_id="verified",
            evidence_type="probe",
            trust_state="probe-verified",
            endpoint_id="openai",
            route_id="openai:known-ok",
            model_id="known-ok",
            provider_model_id="known-ok",
        ),
        EvidenceRecord(
            evidence_id="failed",
            evidence_type="probe",
            trust_state="probe-failed",
            endpoint_id="openai",
            route_id="openai:known-fail",
            model_id="known-fail",
            provider_model_id="known-fail",
        ),
    )

    priority = probe_priority(library, "openai", ["known-fail", "fresh", "known-ok"])

    assert priority == ["fresh", "known-fail"]


def test_promotable_route_update_derives_capabilities_and_profiles_from_probe_verified() -> None:
    route = ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )
    library = _library(
        EvidenceRecord(
            evidence_id="verified",
            evidence_type="probe",
            trust_state="probe-verified",
            endpoint_id="openai",
            route_id="openai:gpt-5",
            model_id="gpt-5",
            provider_model_id="gpt-5",
            method_id="openai_responses",
            request_mapper_id="openai_responses_text",
            input_modalities=["text"],
            output_modalities=["text"],
            candidate_capabilities={
                "tool_protocol": CapabilityValue(value=True, source="probed_verified")
            },
        )
    )

    update = promotable_route_update(library, route)

    assert update.capabilities["tool_protocol"].value is True
    assert update.verified_profiles[0].method_id == "openai_responses"
