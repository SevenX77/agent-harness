"""T4a (read door): every runtime evidence query derives from credentials
``route.evidence`` / ``provider_routes`` — never ``llm_probe_catalog.json``
(P7 read symmetry, requirements R9 / design §4.2).

Pins the read-side seam that replaces the scattered ``load_evidence_library``
readers (research §4 reader table). All queries read ONLY credentials.
"""

from __future__ import annotations

from app.core.adapters.gateway import EvidenceRecord
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.community_catalog import COMMUNITY_PROVENANCE


def _probe_evidence(
    *,
    model_id: str,
    trust_state: str = "probe-verified",
    provenance: str | None = None,
    observed_at: str = "2026-06-01T00:00:00+00:00",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"ev-{model_id}-{trust_state}",
        evidence_type="probe",
        trust_state=trust_state,
        endpoint_id="ep-1",
        model_id=model_id,
        provider_model_id=model_id,
        probe_status="ok" if trust_state == "probe-verified" else "error",
        observed_at=observed_at,
        metadata={"provenance": provenance} if provenance else {},
    )


def _endpoint(
    *,
    endpoint_id: str = "ep-1",
    base_url: str = "https://api.openai.com/v1",  # public allowlisted
) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        display_name=endpoint_id,
        protocol="openai_compatible",
        base_url=base_url,
        api_key="secret",
        status="verified",
    )


def _route(
    model_id: str,
    evidence: list[EvidenceRecord],
    *,
    endpoint_id: str = "ep-1",
    status: str = "unverified_manual",
) -> ProviderRoute:
    return ProviderRoute(
        route_id=f"{endpoint_id}:{model_id}",
        endpoint_id=endpoint_id,
        route_slug=model_id,
        provider_model_id=model_id,
        canonical_id=model_id,
        display_name=model_id,
        status=status,
        evidence=evidence,
    )


def _credentials(
    routes: list[ProviderRoute],
    endpoints: list[ProviderEndpoint] | None = None,
) -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={e.endpoint_id: e for e in (endpoints or [_endpoint()])},
        provider_routes={r.route_id: r for r in routes},
    )


def test_route_is_probe_verified_reads_route_evidence() -> None:
    from app.services.llm_credentials_evidence import route_is_probe_verified

    verified = _route("gpt-5", [_probe_evidence(model_id="gpt-5", trust_state="probe-verified")])
    failed = _route("gpt-4", [_probe_evidence(model_id="gpt-4", trust_state="probe-failed")])
    empty = _route("o1", [])

    assert route_is_probe_verified(verified) is True
    assert route_is_probe_verified(failed) is False
    assert route_is_probe_verified(empty) is False


def test_route_probe_history_returns_probe_records_only() -> None:
    from app.services.llm_credentials_evidence import route_probe_history

    route = _route(
        "gpt-5",
        [
            _probe_evidence(model_id="gpt-5", trust_state="probe-verified"),
            _probe_evidence(model_id="gpt-5", trust_state="probe-failed", observed_at="2026-05-01T00:00:00+00:00"),
            EvidenceRecord(
                evidence_id="obs",
                evidence_type="model_list_observation",
                trust_state="provider-list-observed",
            ),
        ],
    )

    history = route_probe_history(route)

    assert {e.trust_state for e in history} == {"probe-verified", "probe-failed"}
    assert all(e.evidence_type == "probe" for e in history)


def test_probe_evidence_counts_count_probe_only_excluding_observations() -> None:
    # Point 4: the Settings "Local probe evidence" count must be PROBE-only —
    # a legacy provider-list-observed record migrated onto a route must NOT
    # inflate the probe count.
    from app.services.llm_credentials_evidence import probe_evidence_counts

    creds = _credentials(
        [
            _route(
                "gpt-5",
                [
                    _probe_evidence(model_id="gpt-5", trust_state="probe-verified"),
                    EvidenceRecord(
                        evidence_id="obs",
                        evidence_type="model_list_observation",
                        trust_state="provider-list-observed",
                    ),
                ],
            ),
            _route("gpt-4", [_probe_evidence(model_id="gpt-4", trust_state="probe-failed")]),
        ]
    )

    counts = probe_evidence_counts(creds)

    assert counts.probe_records == 2  # the observation record is NOT counted
    assert counts.verified == 1
    assert counts.failed == 1
    assert counts.routes == 2


def test_collect_uploadable_excludes_community_failed_and_non_public() -> None:
    from app.services.llm_credentials_evidence import collect_uploadable

    creds = _credentials(
        [
            _route("gpt-5", [_probe_evidence(model_id="gpt-5", trust_state="probe-verified")]),
            _route("gpt-4", [_probe_evidence(model_id="gpt-4", trust_state="probe-failed")]),
            _route(
                "o1",
                [_probe_evidence(model_id="o1", trust_state="probe-verified", provenance=COMMUNITY_PROVENANCE)],
            ),
            # Point 3: probe-verified but on a NON-public endpoint → no endpoint
            # identity to publish → excluded (don't upload unattributable records).
            _route(
                "local-m",
                [_probe_evidence(model_id="local-m", trust_state="probe-verified")],
                endpoint_id="ep-private",
            ),
        ],
        endpoints=[_endpoint(), _endpoint(endpoint_id="ep-private", base_url="https://internal.example.test/v1")],
    )

    uploads = collect_uploadable(creds)

    # Only the local probe-verified record on a PUBLIC endpoint uploads.
    assert {u.provider_model_id for u in uploads} == {"gpt-5"}
    assert uploads[0].normalized_public_base_url == "https://api.openai.com/v1"
    assert uploads[0].endpoint_fingerprint is not None


def test_endpoint_probe_priority_four_tiers_current_then_historical_then_unknown_then_failed() -> None:
    # Point 1: endpoint Test wants the FEWEST attempts to a green — lead with a
    # known-good model, do NOT skip probe-verified (that is the gateway's
    # discovery ordering, not endpoint Test's). Mirrors llm.py:_endpoint_probe_order.
    from app.services.llm_credentials_evidence import endpoint_probe_priority

    creds = _credentials(
        [
            _route("green-m", [], status="verified"),  # tier 1: currently-verified route
            _route("blue-m", [_probe_evidence(model_id="blue-m", trust_state="probe-verified")]),  # tier 2: historical
            _route("red-m", [_probe_evidence(model_id="red-m", trust_state="probe-failed")]),  # tier 4: failed last
        ]
    )

    ordered = endpoint_probe_priority(creds, "ep-1", ["red-m", "unknown-m", "blue-m", "green-m"])

    assert ordered == ["green-m", "blue-m", "unknown-m", "red-m"]


def test_endpoint_listed_model_ids_are_routes_not_catalog() -> None:
    # Point 2: model-list truth = routes (R3.4). The candidate-source query that
    # replaces known_model_ids_for_endpoint(library, ...) reads routes.
    from app.services.llm_credentials_evidence import endpoint_listed_model_ids

    creds = _credentials(
        [
            _route("gpt-5", []),
            _route("gpt-4", []),
            _route("other", [], endpoint_id="ep-2"),  # different endpoint, excluded
        ],
        endpoints=[_endpoint(), _endpoint(endpoint_id="ep-2")],
    )

    assert endpoint_listed_model_ids(creds, "ep-1") == ["gpt-5", "gpt-4"]
    assert endpoint_listed_model_ids(creds, "ep-2") == ["other"]
