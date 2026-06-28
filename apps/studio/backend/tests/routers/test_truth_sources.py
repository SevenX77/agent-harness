from __future__ import annotations

import json

from app.services.llm_paths import community_catalog_cache_path, credentials_path
from app.services.runtime_activity import record_runtime_activity


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
    assert "community_catalog_cache" in sources
    assert sources["llm_credentials"]["path"] == str(credentials_path())
    assert sources["llm_credentials"]["exists"] is True
    assert sources["community_catalog_cache"]["path"] == str(community_catalog_cache_path())
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
