"""Phase 3: blue historical_ready refs derive from route.evidence (probe-verified only).

T3.1 / problem 4: the Studio adapter must derive projection evidence_refs from
``route.evidence`` — the embedded SSOT — keeping ONLY ``probe-verified`` entries,
NOT ``route.metadata['evidence_refs']`` (the retired link) and NOT
``provider-list-observed``. Fails until ``_route_credential_evidence_refs`` reads
``route.evidence``.
"""

from __future__ import annotations

from app.core.adapters.gateway import GatewayAdapter
from app.models.llm_config import ProviderRoute
from graph_agent_gateway.registry import EvidenceRecord


def _route(
    *,
    evidence: list[EvidenceRecord] | None = None,
    metadata: dict[str, object] | None = None,
) -> ProviderRoute:
    return ProviderRoute(
        route_id="ep-1:gpt-5",
        endpoint_id="ep-1",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="unverified_manual",
        metadata=metadata or {},
        evidence=evidence or [],
    )


def _evidence(
    *,
    trust_state: str,
    evidence_id: str = "ev-1",
    content_hash: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type="probe",
        trust_state=trust_state,  # type: ignore[arg-type]
        route_id="ep-1:gpt-5",
        provider_model_id="gpt-5",
        probe_status="ok",
        content_hash=content_hash,
    )


def test_refs_derive_from_route_evidence_probe_verified() -> None:
    adapter = GatewayAdapter(transport="in_process")
    route = _route(evidence=[_evidence(trust_state="probe-verified", content_hash="sha256:abc")])
    assert adapter._route_credential_evidence_refs(route) == ["sha256:abc"]


def test_refs_fall_back_to_evidence_id_when_no_content_hash() -> None:
    adapter = GatewayAdapter(transport="in_process")
    route = _route(evidence=[_evidence(trust_state="probe-verified", evidence_id="probe-x", content_hash=None)])
    assert adapter._route_credential_evidence_refs(route) == ["probe-x"]


def test_refs_ignore_metadata_evidence_refs() -> None:
    # Phase 3: route.metadata['evidence_refs'] is the RETIRED link, no longer a source.
    adapter = GatewayAdapter(transport="in_process")
    route = _route(metadata={"evidence_refs": ["stale-ref"]}, evidence=[])
    assert adapter._route_credential_evidence_refs(route) == []


def test_refs_exclude_provider_list_observed() -> None:
    # problem 4: only probe-verified contributes to blue; list-observed never does.
    adapter = GatewayAdapter(transport="in_process")
    route = _route(evidence=[_evidence(trust_state="provider-list-observed")])
    assert adapter._route_credential_evidence_refs(route) == []


def test_refs_exclude_probe_failed() -> None:
    adapter = GatewayAdapter(transport="in_process")
    route = _route(evidence=[_evidence(trust_state="probe-failed")])
    assert adapter._route_credential_evidence_refs(route) == []


def test_refs_empty_when_no_evidence() -> None:
    adapter = GatewayAdapter(transport="in_process")
    assert adapter._route_credential_evidence_refs(_route(evidence=[])) == []
