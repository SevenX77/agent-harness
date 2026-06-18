from __future__ import annotations

from datetime import datetime

import httpx
import pytest
from app.models.settings import AppSettings
from app.services.artifact_registry import (
    ArtifactRegistryApiError,
    ArtifactRegistryClient,
    build_publish_metadata,
)


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
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(401, text='{"error": "Unauthorized"}')
            ),
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


@pytest.mark.parametrize(
    ("response", "expected_body"),
    [
        (
            httpx.Response(
                200,
                text="<html>ok</html>",
                headers={"Content-Type": "text/html"},
            ),
            "<html>ok</html>",
        ),
        (httpx.Response(200, json=["not", "a", "dict"]), '["not","a","dict"]'),
    ],
)
def test_upload_artifact_2xx_malformed_response_raises_api_error(
    response: httpx.Response,
    expected_body: str,
) -> None:
    client = ArtifactRegistryClient(
        host="https://registry.example.test",
        token="test-token",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _request: response)),
    )

    with pytest.raises(ArtifactRegistryApiError) as exc_info:
        client.upload_artifact(skill_id="demo-skill", package=b"zip", metadata={})

    assert exc_info.value.status_code == 200
    assert exc_info.value.body == expected_body


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


def test_build_publish_metadata_returns_required_keys() -> None:
    metadata = build_publish_metadata("demo-skill", AppSettings(user_id="alice"))

    assert metadata["skill_id"] == "demo-skill"
    assert metadata["author"] == "alice"
    assert metadata["version"] == "1.0.0"
    created_at = datetime.fromisoformat(str(metadata["created_at"]))
    assert created_at.tzinfo is not None


def test_build_publish_metadata_raises_when_user_id_empty() -> None:
    with pytest.raises(ValueError, match="Publish requires non-empty user_id in app_settings"):
        build_publish_metadata("demo-skill", AppSettings(user_id=""))


def test_build_publish_metadata_uses_custom_version() -> None:
    metadata = build_publish_metadata("demo-skill", AppSettings(user_id="alice"), version="2.3.4")

    assert metadata["version"] == "2.3.4"
