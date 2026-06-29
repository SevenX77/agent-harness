"""Phase 5: verified community evidence merges into credentials route.evidence.

The community catalog is a wire/privacy/mapping layer ONLY; it never writes
credentials. Downloaded verified evidence is merged into existing routes
(matched by endpoint host + provider_model_id) via ``merge_route_evidence``,
carrying ``provenance="community-catalog"`` so the UI projects blue but
``collect_uploadable`` never re-uploads it. No ``metadata["evidence_refs"]``,
no new endpoints/routes, no green.
"""

from __future__ import annotations

from app.core.adapters.gateway import compute_evidence_content_hash
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.community_catalog import COMMUNITY_PROVENANCE, parse_catalog_evidence


def _credentials_with_route(*, base_url: str = "https://api.openai.com/v1", model_id: str = "gpt-4o") -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={
            "ep": ProviderEndpoint(
                endpoint_id="ep",
                display_name="EP",
                protocol="openai_compatible",
                base_url=base_url,
                api_key="secret",
                status="verified",
            )
        },
        provider_routes={
            f"ep:{model_id}": ProviderRoute(
                route_id=f"ep:{model_id}",
                endpoint_id="ep",
                route_slug=model_id,
                provider_model_id=model_id,
                canonical_id=model_id,
                status="unverified_manual",
            )
        },
    )


def _wire(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "evidence_type": "probe_result",
        "trust_state": "probe-verified",
        "evidence_id": "cat-1",
        "normalized_public_base_url": "https://api.openai.com",
        "provider_model_id": "gpt-4o",
        "model_id": "gpt-4o",
        "probe_status": "ok",
    }
    base.update(overrides)
    return base


def test_parse_sets_formal_normalized_url_and_it_affects_content_hash() -> None:
    # Red test #1: the published endpoint identity must land on the FORMAL field
    # EvidenceRecord.normalized_public_base_url (not only metadata), so two otherwise
    # identical records on different endpoints hash differently.
    rec_a = parse_catalog_evidence(_wire(evidence_id="a", normalized_public_base_url="https://api.openai.com"))
    rec_b = parse_catalog_evidence(_wire(evidence_id="b", normalized_public_base_url="https://api.anthropic.com"))

    assert rec_a.normalized_public_base_url == "https://api.openai.com"
    assert rec_b.normalized_public_base_url == "https://api.anthropic.com"
    assert compute_evidence_content_hash(rec_a) != compute_evidence_content_hash(rec_b)


def test_parse_stamps_community_provenance() -> None:
    rec = parse_catalog_evidence(_wire())
    assert rec.metadata.get("provenance") == COMMUNITY_PROVENANCE


def test_merge_matches_existing_route_into_evidence_and_projects_blue() -> None:
    # Host-tolerant match (route base_url has /v1, record is bare host) + model id →
    # merged ONTO route.evidence via merge_route_evidence (no metadata evidence_refs),
    # probe-verified community evidence → projects blue, provenance preserved.
    from app.services.community_catalog_runtime import merge_community_evidence_into_credentials
    from app.services.llm_credentials_evidence import route_is_probe_verified

    creds = _credentials_with_route(base_url="https://api.openai.com/v1", model_id="gpt-4o")
    record = parse_catalog_evidence(_wire(normalized_public_base_url="https://api.openai.com", provider_model_id="gpt-4o"))

    updated = merge_community_evidence_into_credentials(creds, [record])

    assert updated == 1
    route = creds.provider_routes["ep:gpt-4o"]
    assert route_is_probe_verified(route)
    assert "evidence_refs" not in route.metadata
    assert route.status == "unverified_manual"  # community evidence never sets green
    assert route.evidence[0].metadata.get("provenance") == COMMUNITY_PROVENANCE


def test_merge_does_not_create_routes_when_no_match() -> None:
    from app.services.community_catalog_runtime import merge_community_evidence_into_credentials

    creds = LLMCredentialsFile()  # no endpoints/routes
    record = parse_catalog_evidence(_wire())

    updated = merge_community_evidence_into_credentials(creds, [record])

    assert updated == 0
    assert creds.provider_routes == {}


def test_merge_is_idempotent_by_content_hash() -> None:
    from app.services.community_catalog_runtime import merge_community_evidence_into_credentials

    creds = _credentials_with_route(model_id="gpt-4o")
    record = parse_catalog_evidence(_wire(provider_model_id="gpt-4o"))

    first = merge_community_evidence_into_credentials(creds, [record])
    second = merge_community_evidence_into_credentials(creds, [record])

    # Same content_hash → deduped: exactly one evidence record on the route.
    assert len(creds.provider_routes["ep:gpt-4o"].evidence) == 1
    # Phase 5 cleanup: the count is the ACTUAL changed-route count, not the number of
    # match attempts — a re-sync that changes nothing reports 0 (so the runtime-activity
    # ``merged_route_count`` never inflates on an unchanged catalog).
    assert first == 1
    assert second == 0

