from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx
import pytest

from app.models.settings import AppSettings
from app.services.artifact_registry import (
    ArtifactRegistryApiError,
    ArtifactRegistryClient,
    build_publish_metadata,
    build_publish_package,
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


def test_build_publish_package_excludes_workspace(tmp_path: Path) -> None:
    skill_dir = _skill_dir(tmp_path)
    _write(skill_dir / "SKILL.md", "# Demo\n")
    _write(skill_dir / ".workspace" / "runs" / "latest" / "x.json", "{}")
    _write(skill_dir / ".workspace" / "golden" / "y.json", "{}")

    names = _zip_names(build_publish_package(skill_dir))

    assert "SKILL.md" in names
    assert all(not name.startswith(".workspace/") for name in names)


def test_build_publish_package_excludes_git_and_kiro(tmp_path: Path) -> None:
    skill_dir = _skill_dir(tmp_path)
    _write(skill_dir / "SKILL.md", "# Demo\n")
    _write(skill_dir / ".git" / "config", "[remote]\n")
    _write(skill_dir / ".kiro" / "specs" / "x.md", "# spec\n")

    names = _zip_names(build_publish_package(skill_dir))

    assert "SKILL.md" in names
    assert all(not name.startswith(".git/") for name in names)
    assert all(not name.startswith(".kiro/") for name in names)


def test_build_publish_package_excludes_pycache_and_pyc(tmp_path: Path) -> None:
    skill_dir = _skill_dir(tmp_path)
    _write(skill_dir / "SKILL.md", "# Demo\n")
    _write(skill_dir / "__pycache__" / "m.cpython-312.pyc", "compiled")
    _write(skill_dir / "foo.pyc", "compiled")

    names = _zip_names(build_publish_package(skill_dir))

    assert "SKILL.md" in names
    assert "__pycache__/m.cpython-312.pyc" not in names
    assert "foo.pyc" not in names


def test_build_publish_package_includes_script_and_example(tmp_path: Path) -> None:
    skill_dir = _skill_dir(tmp_path)
    _write(skill_dir / "SKILL.md", "# Demo\n")
    _write(skill_dir / "script" / "run.py", "def run():\n    return True\n")
    _write(skill_dir / "example" / "golden.json", "{}")
    _write(skill_dir / "README.md", "# Readme\n")

    names = _zip_names(build_publish_package(skill_dir))

    assert {"SKILL.md", "script/run.py", "example/golden.json", "README.md"} <= names


def test_build_publish_package_raises_when_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Publish skill_dir must be an existing directory"):
        build_publish_package(tmp_path / "missing")


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


def _skill_dir(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    return skill_dir


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _zip_names(payload: bytes) -> set[str]:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        return set(archive.namelist())
