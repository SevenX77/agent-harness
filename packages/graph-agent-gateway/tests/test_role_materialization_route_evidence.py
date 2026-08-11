"""Phase 3: gateway role materialization derives evidence refs from route.evidence.

The SDK ``role_materialization`` read path must match the Studio adapter's UI
projection: blue ``historical_ready`` refs come from probe-verified evidence
embedded ON the route (``route.evidence``), NOT ``route.metadata`` (the retired
link). Otherwise an endpoint-failed route carrying probe-verified evidence would
project ``historical_ready`` for the UI yet be SKIPPED by role materialization —
a silent fallback_chain hole.
"""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr


def test_refs_read_route_evidence_probe_verified_ignoring_metadata() -> None:
    from graph_agent_gateway.registry import EvidenceRecord
    from graph_agent_gateway.role_materialization import _route_credential_evidence_refs

    route = SimpleNamespace(
        evidence=[
            EvidenceRecord(
                evidence_id="probe-x",
                evidence_type="probe",
                trust_state="probe-verified",
                content_hash="sha256:abc",
            )
        ],
        metadata={"evidence_refs": ["stale-metadata-ref"]},  # retired link, must be ignored
    )

    assert _route_credential_evidence_refs(route) == ["sha256:abc"]


def test_refs_fall_back_to_evidence_id_without_content_hash() -> None:
    from graph_agent_gateway.registry import EvidenceRecord
    from graph_agent_gateway.role_materialization import _route_credential_evidence_refs

    route = SimpleNamespace(
        evidence=[EvidenceRecord(evidence_id="probe-y", evidence_type="probe", trust_state="probe-verified")],
        metadata={},
    )

    assert _route_credential_evidence_refs(route) == ["probe-y"]


def test_refs_exclude_non_probe_verified() -> None:
    from graph_agent_gateway.registry import EvidenceRecord
    from graph_agent_gateway.role_materialization import _route_credential_evidence_refs

    route = SimpleNamespace(
        evidence=[
            EvidenceRecord(evidence_id="lo", evidence_type="model_list_observation", trust_state="provider-list-observed"),
            EvidenceRecord(evidence_id="pf", evidence_type="probe", trust_state="probe-failed"),
        ],
        metadata={},
    )

    assert _route_credential_evidence_refs(route) == []


def test_materialize_role_keeps_endpoint_failed_route_with_probe_verified_evidence() -> None:
    # The core regression: endpoint failed + probe-verified route.evidence must
    # project historical_ready (not failed), so the route stays in the chain.
    from graph_agent_gateway.registry import EvidenceRecord
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = SimpleNamespace(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="unverified_manual",
        capabilities={},
        verified_profiles=[],
        metadata={},
        evidence=[
            EvidenceRecord(evidence_id="probe-openai-gpt5", evidence_type="probe", trust_state="probe-verified")
        ],
    )
    endpoint = SimpleNamespace(
        endpoint_id="openai",
        status="failed",  # endpoint FAILED
        api_key=SecretStr("secret"),
        metadata={},
    )
    role = SimpleNamespace(
        model_groups=[
            SimpleNamespace(canonical_id="gpt-5", provider_models=[SimpleNamespace(route_id="openai:gpt-5")])
        ],
        model_fallback_enabled=True,
    )

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=role,
            credentials=SimpleNamespace(
                provider_endpoints={"openai": endpoint},
                provider_routes={"openai:gpt-5": route},
            ),
            health_store=SimpleNamespace(get_active_circuits=lambda **_: []),
        )
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
