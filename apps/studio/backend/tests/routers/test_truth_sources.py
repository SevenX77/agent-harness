from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.services.llm_paths import credentials_path
from app.services.runtime_activity import record_runtime_activity


def test_runtime_activity_recorded_at_is_utc(client) -> None:
    # Design §7.1 runtime-truth-sources: the activity log must timestamp in UTC so
    # entries correlate 1:1 with the credentials / role-test truth files (which
    # already record UTC). A local-offset stamp made cross-file timelines lie.
    entry = record_runtime_activity(
        source_id="llm_credentials",
        action="endpoint_test",
        message="utc stamp check",
    )
    recorded_at = datetime.fromisoformat(entry["recorded_at"])
    assert recorded_at.utcoffset() == timedelta(0)


def _flatten_sources(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    sections = payload["sections"]
    assert isinstance(sections, list)
    return {
        source["id"]: source
        for section in sections
        for source in section["sources"]
    }


def test_truth_sources_lists_store_files_and_logs(client) -> None:
    credentials_path().parent.mkdir(parents=True, exist_ok=True)
    credentials_path().write_text(
        json.dumps({"schema_version": 4, "endpoints": []}),
        encoding="utf-8",
    )
    record_runtime_activity(
        source_id="llm_credentials",
        action="endpoint_test",
        message="Tested endpoint deepseek-official and promoted catalog evidence.",
        changes={
            "endpoint_id": "deepseek-official",
            "status": "verified",
            "promoted_catalog_records": 2,
        },
    )

    response = client.get("/api/system/truth-sources")

    assert response.status_code == 200
    sources = _flatten_sources(response.json())
    assert "llm_credentials" in sources
    # Phase 9: the three retired legacy catalog files are no longer surfaced as truth sources.
    assert "llm_probe_catalog" not in sources
    assert "community_catalog_cache" not in sources
    assert "community_upload_queue" not in sources
    assert sources["llm_credentials"]["path"] == str(credentials_path())
    assert sources["llm_credentials"]["exists"] is True
    assert sources["llm_credentials"]["logs"][0]["action"] == "endpoint_test"
    assert sources["llm_credentials"]["logs"][0]["changes"]["promoted_catalog_records"] == 2


def test_truth_source_content_reads_known_text_sources(client) -> None:
    credentials_path().parent.mkdir(parents=True, exist_ok=True)
    credentials_path().write_text(
        json.dumps({"schema_version": 4, "endpoints": [{"id": "anthropic-official"}]}),
        encoding="utf-8",
    )

    response = client.get("/api/system/truth-sources/llm_credentials/content")

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == "llm_credentials"
    assert body["path"] == str(credentials_path())
    assert '"anthropic-official"' in body["content"]


def test_truth_source_content_rejects_unknown_source(client) -> None:
    response = client.get("/api/system/truth-sources/not-real/content")

    assert response.status_code == 404


def test_community_catalog_config_reflects_backend_config(client, monkeypatch) -> None:
    # R-G3 / R10: the endpoint exposes the baked-in manifest URL + signing pubkey
    # (public, no secret) so the UI can show them read-only. It faithfully reflects
    # backend config (here monkeypatched, since tests run with these blanked out).
    from types import SimpleNamespace

    from app.routers import system as system_router

    monkeypatch.setattr(
        system_router,
        "get_backend_config",
        lambda: SimpleNamespace(
            community_catalog_manifest_url="https://example.test/manifest.json",
            community_catalog_signing_pubkey="ab" * 32,
        ),
    )

    response = client.get("/api/system/community-catalog-config")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "manifest_url": "https://example.test/manifest.json",
        "signing_pubkey": "ab" * 32,
    }
