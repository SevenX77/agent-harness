"""N6/F2 + 设计§4: publish is not hard-blocked by an incomplete Settings gate.

The local product publish is the MVP1 safety net and must proceed even when
``user_id`` is not configured. Only the *remote registry sync* leg depends on
Settings (it needs an author); when Settings are incomplete that leg is skipped
with a clear, non-blocking ``remote_sync`` status — the local release still
commits and returns 200.
"""

from __future__ import annotations

from pathlib import Path

from app.core.adapters.product_store_local import LocalProductArtifactStore
from app.core.backends import get_registry_client
from fastapi.testclient import TestClient

from .test_publish import FakeRegistry, _write_settings


def test_publish_without_user_id_is_not_blocked_and_returns_local_release(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["extra"]["package_kind"] == "product_artifact"
    assert body["extra"]["release_version"] == "1.0.0"
    assert registry.calls == []

    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None


def test_publish_without_user_id_skips_registry_sync_with_clear_reason(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(host="https://registry.example.test", token="registry-token")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    remote_sync = body["extra"]["remote_sync"]
    assert remote_sync["status"] == "skipped"
    assert remote_sync["reason"] == "app_settings_incomplete"
    # The registry must not be contacted when the publish identity is missing.
    assert registry.calls == []

    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
