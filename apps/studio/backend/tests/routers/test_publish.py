from __future__ import annotations

from typing import Any

import httpx
from app.core.backends import get_registry_client
from app.services.artifact_registry import ArtifactRegistryApiError
from fastapi.testclient import TestClient


def test_publish_skill_success(client: TestClient) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Published to registry"
    assert body["artifact_id"] == "art-123"
    assert body["extra"]["version"] == "1.0.0"
    assert body["extra"]["skill_id"] == "text-segmentation"
    assert body["extra"]["package_bytes"] > 0
    assert registry.calls[0]["skill_id"] == "text-segmentation"
    assert registry.calls[0]["metadata"]["author"] == "alice"
    assert registry.calls[0]["metadata"]["version"] == "1.0.0"


def test_publish_skill_app_settings_incomplete(client: TestClient) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 400
    assert response.json()["error_code"] == "APP_SETTINGS_INCOMPLETE"
    assert response.json()["details"] == {"field": "user_id"}
    assert registry.calls == []


def test_publish_skill_registry_not_configured(client: TestClient) -> None:
    registry = FakeRegistry(host="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 400
    assert response.json()["error_code"] == "REGISTRY_NOT_CONFIGURED"
    assert response.json()["details"] == {"field": "registry_host"}
    assert registry.calls == []


def test_publish_skill_registry_api_error_502(client: TestClient) -> None:
    registry = FakeRegistry(error=ArtifactRegistryApiError(status_code=401, body="unauthorized"))
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 502
    body = response.json()
    assert body["error_code"] == "REGISTRY_API_ERROR"
    assert body["details"] == {"status_code": 401, "body": "unauthorized"}


def test_publish_skill_registry_network_error_503(client: TestClient) -> None:
    request = httpx.Request("POST", "https://registry.example.test/api/v1/artifacts")
    registry = FakeRegistry(error=httpx.ConnectError("DNS failure", request=request))
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 503
    assert response.json()["error_code"] == "REGISTRY_NETWORK_ERROR"
    assert "DNS failure" in response.json()["message"]


def test_publish_skill_custom_version(client: TestClient) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={"version": "2.0.0"})

    assert response.status_code == 200
    assert response.json()["extra"]["version"] == "2.0.0"
    assert registry.calls[0]["metadata"]["version"] == "2.0.0"


class FakeRegistry:
    def __init__(
        self,
        *,
        host: str = "https://registry.example.test",
        token: str = "registry-token",
        error: Exception | None = None,
    ) -> None:
        self.host = host
        self.token = token
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def upload_artifact(
        self,
        *,
        skill_id: str,
        package: bytes,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"skill_id": skill_id, "package": package, "metadata": metadata})
        if self.error is not None:
            raise self.error
        return {"artifact_id": "art-123"}


def _write_settings(client: TestClient, *, user_id: str) -> None:
    response = client.put(
        "/api/settings",
        json={"user_id": user_id, "gitea_host": "https://gitea.example.com"},
    )
    assert response.status_code == 200
