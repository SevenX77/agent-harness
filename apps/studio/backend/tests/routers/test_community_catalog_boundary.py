"""Phase 2a R8: boundary regression guards.

Adding the opt-in community upload + verified sync paths must not change the
pre-existing endpoints. ``/catalog/share`` stays local-export-only even when the
community gate is fully configured, and ``/catalog/repository/ensure`` keeps its
prior contract.
"""

from __future__ import annotations

import pytest
from app.core.backends import clear_backend_caches
from fastapi.testclient import TestClient


def test_share_endpoint_stays_local_export_only(client: TestClient) -> None:
    body = client.post("/api/llm/catalog/share").json()
    assert body["sharing_mode"] == "local_export_only"
    assert body["auto_upload_enabled"] is False


def test_share_endpoint_unaffected_when_community_upload_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The critical R8 guard: enabling community upload must NOT make /catalog/share
    # start uploading. Share remains a pure local export.
    monkeypatch.setenv("STUDIO_COMMUNITY_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("STUDIO_COMMUNITY_GATE_URL", "https://gate.example.org")
    clear_backend_caches()
    body = client.post("/api/llm/catalog/share").json()
    assert body["sharing_mode"] == "local_export_only"
    assert body["auto_upload_enabled"] is False


def test_repository_ensure_is_retired_noop(client: TestClient) -> None:
    # Phase 9: the GitHub-repo probe-catalog concept is retired. The endpoint is a no-op
    # that never reaches the network and never creates llm_probe_catalog.json — it just
    # reports disabled (no GitHub token check anymore).
    response = client.post("/api/llm/catalog/repository/ensure")
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
