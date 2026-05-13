from __future__ import annotations

import httpx
import pytest

from app.services.artifact_registry import ArtifactRegistryApiError, ArtifactRegistryClient


def test_upload_artifact_success_returns_server_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert request.method == "POST"
        assert request.url.path == "/api/v1/artifacts"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert b'name="metadata"' in body
        assert b'"skill_id": "demo-skill"' in body
        assert b'"version": "1.0.0"' in body
        assert b'name="package"; filename="demo-skill.zip"' in body
        assert b"PK\x03\x04zip-bytes" in body
        assert "multipart/form-data" in request.headers["Content-Type"]
        return httpx.Response(200, json={"artifact_id": "art-123", "status": "uploaded"})

    client = ArtifactRegistryClient(
        host="https://registry.example.test",
        token="test-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.upload_artifact(
        skill_id="demo-skill",
        package=b"PK\x03\x04zip-bytes",
        metadata={"version": "1.0.0"},
    )

    assert result == {"artifact_id": "art-123", "status": "uploaded"}


def test_upload_artifact_401_raises_api_error() -> None:
    client = ArtifactRegistryClient(
        host="https://registry.example.test",
        token="bad-token",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(401, text='{"error": "Unauthorized"}')),
        ),
    )

    with pytest.raises(ArtifactRegistryApiError) as exc_info:
        client.upload_artifact(skill_id="demo-skill", package=b"zip", metadata={})

    assert exc_info.value.status_code == 401
    assert "Unauthorized" in exc_info.value.body


def test_upload_artifact_500_raises_api_error() -> None:
    client = ArtifactRegistryClient(
        host="https://registry.example.test",
        token="test-token",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(500, text='{"error": "Internal Server Error"}'),
            ),
        ),
    )

    with pytest.raises(ArtifactRegistryApiError) as exc_info:
        client.upload_artifact(skill_id="demo-skill", package=b"zip", metadata={})

    assert exc_info.value.status_code == 500
    assert "Internal Server Error" in exc_info.value.body


def test_upload_artifact_network_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS failure", request=request)

    client = ArtifactRegistryClient(
        host="https://registry.example.test",
        token="test-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(httpx.RequestError):
        client.upload_artifact(skill_id="demo-skill", package=b"zip", metadata={})


def test_upload_artifact_requires_host_and_token() -> None:
    with pytest.raises(ValueError, match="Artifact Registry host is not configured"):
        ArtifactRegistryClient(host="", token="test-token").upload_artifact(
            skill_id="demo-skill",
            package=b"zip",
            metadata={},
        )

    with pytest.raises(ValueError, match="Artifact Registry token is not configured"):
        ArtifactRegistryClient(host="https://registry.example.test", token="").upload_artifact(
            skill_id="demo-skill",
            package=b"zip",
            metadata={},
        )
