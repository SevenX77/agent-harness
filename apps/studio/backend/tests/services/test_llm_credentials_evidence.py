"""Red tests for credentials-embedded evidence — Studio LLM credentials/catalog SSOT.

T2.1 (Phase 2): pins the v5 schema carrying ``route.evidence`` (R1.2), the
content-hash dedup helper ``merge_route_evidence`` (R2.2), evidence cleanup on
route delete (R1.3), and the minimal ``last_remote_catalog_sync`` marker (R1.4).
Fails until T2.3 adds the schema + helper.
"""

from __future__ import annotations

from pathlib import Path

from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.llm_credentials import delete_route, load_credentials, save_credentials
from app.services.llm_credentials_evidence import merge_route_evidence
from graph_agent_gateway.registry import (
    EvidenceRecord,
    compute_evidence_content_hash,
)


def _endpoint() -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id="openai-direct",
        display_name="OpenAI Direct",
        protocol="openai_compatible",
        base_url="https://api.example.com/v1",
    )


def _route() -> ProviderRoute:
    return ProviderRoute(
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )


def _evidence(observed_at: str, **overrides: object) -> EvidenceRecord:
    base: dict[str, object] = {
        "evidence_id": f"evidence-{observed_at}",
        "evidence_type": "probe",
        "trust_state": "probe-verified",
        "normalized_public_base_url": "https://api.example.com/v1",
        "provider_model_id": "gpt-5",
        "model_id": "gpt-5",
        "method_id": "chat_completions",
        "request_mapper_id": "openai_chat",
        "probe_status": "ok",
        "capability_family": "language",
        "observed_at": observed_at,
    }
    base.update(overrides)
    return EvidenceRecord(**base)  # type: ignore[arg-type]


def _v5_credentials(route: ProviderRoute) -> LLMCredentialsFile:
    return LLMCredentialsFile(
        schema_version=5,
        provider_endpoints={"openai-direct": _endpoint()},
        provider_routes={route.route_id: route},
    )


def test_merge_dedupes_same_semantics_and_keeps_latest_observed_at() -> None:
    # R2.2-AC1: same-semantics evidence collapses to one, newest observed_at wins.
    route = merge_route_evidence(_route(), _evidence("2026-06-01T00:00:00Z"))
    assert len(route.evidence) == 1
    route = merge_route_evidence(route, _evidence("2026-06-29T00:00:00Z"))
    assert len(route.evidence) == 1
    assert route.evidence[0].observed_at == "2026-06-29T00:00:00Z"


def test_merge_keeps_distinct_semantics() -> None:
    route = merge_route_evidence(_route(), _evidence("2026-06-01T00:00:00Z"))
    route = merge_route_evidence(route, _evidence("2026-06-02T00:00:00Z", method_id="responses"))
    assert len(route.evidence) == 2


def test_merge_stamps_content_hash_on_write() -> None:
    rec = _evidence("2026-06-01T00:00:00Z")
    assert rec.content_hash is None
    route = merge_route_evidence(_route(), rec)
    assert route.evidence[0].content_hash == compute_evidence_content_hash(rec)


def test_v5_credentials_roundtrip_preserves_route_evidence(tmp_path: Path) -> None:
    # R1.2-AC1: load→save→load keeps route.evidence byte-stable.
    route = merge_route_evidence(_route(), _evidence("2026-06-01T00:00:00Z"))
    path = tmp_path / "llm_credentials.json"
    save_credentials(_v5_credentials(route), path)
    loaded = load_credentials(path)
    assert loaded.schema_version == 5
    reloaded = loaded.provider_routes["openai-direct:gpt-5"]
    assert len(reloaded.evidence) == 1
    assert reloaded.evidence[0].content_hash == route.evidence[0].content_hash


def test_delete_route_drops_its_evidence(tmp_path: Path) -> None:
    # R1.3-AC1: evidence lives on the route; deleting the route removes it.
    route = merge_route_evidence(_route(), _evidence("2026-06-01T00:00:00Z"))
    path = tmp_path / "llm_credentials.json"
    save_credentials(_v5_credentials(route), path)
    delete_route("openai-direct:gpt-5", path=path)
    loaded = load_credentials(path)
    assert "openai-direct:gpt-5" not in loaded.provider_routes


def test_last_remote_catalog_sync_marker_holds_only_three_scalars(tmp_path: Path) -> None:
    # R1.4-AC1: top-level remote-sync metadata is three scalars, nothing more.
    from app.models.llm_config import RemoteCatalogSyncMarker

    creds = LLMCredentialsFile(
        schema_version=5,
        last_remote_catalog_sync=RemoteCatalogSyncMarker(
            etag='W/"abc"',
            generated_at="2026-06-29T00:00:00Z",
            last_synced_at="2026-06-29T01:00:00Z",
        ),
    )
    path = tmp_path / "llm_credentials.json"
    save_credentials(creds, path)
    marker = load_credentials(path).last_remote_catalog_sync
    assert marker is not None
    assert marker.etag == 'W/"abc"'
    assert set(marker.model_dump().keys()) == {"etag", "generated_at", "last_synced_at"}


def test_merge_stamps_content_hash_on_preexisting_unhashed_evidence() -> None:
    # P2: an existing record without content_hash must get hashed on merge, even when
    # the incoming record is a DIFFERENT semantic (appended, not replaced).
    unhashed = _evidence("2026-06-01T00:00:00Z")
    route = _route().model_copy(update={"evidence": [unhashed]})
    assert route.evidence[0].content_hash is None

    route = merge_route_evidence(route, _evidence("2026-06-02T00:00:00Z", method_id="responses"))

    assert len(route.evidence) == 2
    assert all(ev.content_hash is not None for ev in route.evidence)


def test_merge_recomputes_stale_existing_content_hash_for_dedup() -> None:
    # P2: an existing record carrying a WRONG/stale content_hash must be re-hashed so a
    # same-semantics incoming record dedups against its TRUE hash, not the stale one.
    stale = _evidence("2026-06-01T00:00:00Z").model_copy(update={"content_hash": "sha256:deadbeef"})
    route = _route().model_copy(update={"evidence": [stale]})

    route = merge_route_evidence(route, _evidence("2026-06-02T00:00:00Z"))

    assert len(route.evidence) == 1


def test_merge_compares_observed_at_chronologically_not_lexically() -> None:
    # P3: mixed tz formats must compare by real instant, not string order. The existing
    # record is LATER in real time (13:00 UTC) but lexically "smaller"; the incoming is
    # earlier (12:00 UTC) but lexically "larger".
    later_real = _evidence("2026-06-01T11:00:00-02:00")  # 13:00 UTC
    earlier_real = _evidence("2026-06-01T12:00:00Z")  # 12:00 UTC
    route = _route().model_copy(update={"evidence": [later_real]})

    route = merge_route_evidence(route, earlier_real)

    assert len(route.evidence) == 1
    assert route.evidence[0].observed_at == "2026-06-01T11:00:00-02:00"
