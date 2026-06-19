from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.core.adapters.http_transport import StudioAdapterError
from app.core.adapters.product_store_local import LocalProductArtifactStore
from app.core.backends import get_registry_client
from app.main import create_app
from app.services.artifact_registry import ArtifactRegistryApiError, ArtifactRegistryClient
from app.services.git_local import (
    GitCommandError,
    GitCommandResult,
    initialize_skill_repository,
    run_git,
)
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
    assert body["artifact_id"] == "text-segmentation"
    assert body["extra"]["version"] == "1.0.0"
    assert body["extra"]["skill_id"] == "text-segmentation"
    assert body["extra"]["release_version"] == "1.0.0"
    assert body["extra"]["artifact_id"] == "text-segmentation"
    assert body["extra"]["remote_sync"] == {"status": "succeeded"}
    assert body["extra"]["registry_artifact_id"] == "art-123"
    assert "package_bytes" not in body["extra"]
    assert body["extra"]["package_kind"] == "product_artifact"
    artifact_ref = body["extra"]["artifact_ref"]
    assert artifact_ref["artifact_id"] == "text-segmentation"
    assert artifact_ref["store"] == "product"
    assert artifact_ref["content_hash"].startswith("sha256:")
    assert registry.calls[0]["skill_id"] == "text-segmentation"
    assert registry.calls[0]["metadata"]["author"] == "alice"
    assert registry.calls[0]["metadata"]["version"] == "1.0.0"
    assert registry.calls[0]["metadata"]["package_kind"] == "product_artifact"
    assert registry.calls[0]["metadata"]["artifact_ref"] == artifact_ref


def test_publish_skill_app_settings_incomplete(client: TestClient) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 400
    assert response.json()["error_code"] == "APP_SETTINGS_INCOMPLETE"
    assert response.json()["details"] == {"field": "user_id"}
    assert registry.calls == []


def test_publish_skill_unconfigured_registry_returns_local_product_release(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Published to local product store"
    assert body["artifact_id"] == "text-segmentation"
    assert body["extra"]["version"] == "1.0.0"
    assert body["extra"]["release_version"] == "1.0.0"
    assert body["extra"]["skill_id"] == "text-segmentation"
    assert body["extra"]["artifact_id"] == "text-segmentation"
    assert "package_bytes" not in body["extra"]
    assert body["extra"]["package_kind"] == "product_artifact"
    assert body["extra"]["remote_sync"] == {
        "status": "skipped",
        "reason": "registry_not_configured",
    }
    artifact_ref = body["extra"]["artifact_ref"]
    assert artifact_ref["artifact_id"] == "text-segmentation"
    assert artifact_ref["store"] == "product"
    assert artifact_ref["content_hash"].startswith("sha256:")
    assert registry.calls == []

    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
    assert release["remote_sync"] == {
        "status": "skipped",
        "reason": "registry_not_configured",
    }
    [listed_release] = store.list_releases("text-segmentation")
    assert listed_release["remote_sync"] == {
        "status": "skipped",
        "reason": "registry_not_configured",
    }


def test_release_list_and_detail_return_committed_product_manifest_identity(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})

    assert publish_response.status_code == 200
    published = publish_response.json()["extra"]
    releases_dir = studio_roots[1] / "default" / "releases" / "text-segmentation"
    (releases_dir / "9.9.9.stage").write_text(
        """
        {
          "release_version": "9.9.9",
          "artifact_ref": {
            "artifact_id": "staged-only",
            "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "manifest_ref": "manifests/staged-only.json",
            "store": "product"
          },
          "idempotency_key": "staged"
        }
        """,
        encoding="utf-8",
    )

    list_response = client.get("/api/skills/text-segmentation/releases")
    detail_response = client.get("/api/skills/text-segmentation/releases/1.0.0")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json() == [detail_response.json()]
    release = detail_response.json()
    assert release["release_version"] == "1.0.0"
    assert release["artifact_id"] == "text-segmentation"
    assert release["content_hash"] == published["content_hash"]
    assert release["content_hash"].startswith("sha256:")
    assert release["manifest_ref"] == published["manifest_ref"]
    assert release["artifact_ref"]["store"] == "product"
    assert release["artifact_ref"]["artifact_id"] == "text-segmentation"
    assert release["artifact_ref"]["content_hash"] == published["content_hash"]
    assert release["artifact_ref"]["manifest_ref"] == published["manifest_ref"]
    assert release["remote_sync"] == {
        "status": "skipped",
        "reason": "registry_not_configured",
    }
    assert isinstance(release["created_at"], str)
    assert datetime.fromisoformat(release["created_at"]).tzinfo is not None
    assert "package_bytes" not in str(release)
    assert "source_path" not in str(release)
    assert "staged-only" not in str(list_response.json())


def test_release_run_starts_from_committed_product_artifact_without_recompiling_source(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import queue

    from app.services.run_manager import run_manager

    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})
    assert publish_response.status_code == 200
    release = LocalProductArtifactStore(root=studio_roots[1] / "default").get_release(
        "text-segmentation",
        "1.0.0",
    )
    assert release is not None
    release_artifact_ref = release["artifact_ref"]
    expected_artifact_ref = {**release_artifact_ref, "version": "1.0.0"}
    shutil.rmtree(studio_roots[0] / "text-segmentation")

    class FailIfCompileAdapter:
        def compile(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("release run must not compile current workspace source")

    class InlineProcess:
        def __init__(self, target: Any, args: tuple[Any, ...]) -> None:
            self.target = target
            self.args = args

        def start(self) -> None:
            self.target(*self.args)

        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:
            return None

    captured: dict[str, Any] = {}

    def fake_release_worker(
        skill_id: str,
        run_dir_raw: str,
        inputs: dict[str, Any],
        process_queue: Any,
        art_ref: dict[str, Any] | None = None,
    ) -> None:
        captured["skill_id"] = skill_id
        captured["run_dir_raw"] = run_dir_raw
        captured["inputs"] = inputs
        captured["art_ref"] = art_ref
        process_queue.put({"type": "status", "status": "success", "metrics": {}})

    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_release_worker)
    import app.core.adapters.transport_factory as transport_factory

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FailIfCompileAdapter())

    response = client.post(
        "/api/skills/text-segmentation/releases/1.0.0/runs",
        json={"input_data": {"input_text": "from release"}},
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "running"
    assert captured["skill_id"] == "text-segmentation"
    assert captured["inputs"] == {"input_text": "from release"}
    assert captured["art_ref"] == expected_artifact_ref


def test_release_run_missing_product_blob_returns_typed_artifact_not_found_without_source_fallback(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})
    assert publish_response.status_code == 200
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
    artifact_ref = release["artifact_ref"]
    store.blob_path(artifact_ref["content_hash"]).unlink()
    shutil.rmtree(studio_roots[0] / "text-segmentation")

    class FailIfCompileAdapter:
        def compile(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("missing product artifact must not compile current workspace source")

    import app.core.adapters.transport_factory as transport_factory

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FailIfCompileAdapter())

    response = client.post(
        "/api/skills/text-segmentation/releases/1.0.0/runs",
        json={"input_data": {"input_text": "from release"}},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "artifact.not_found"
    assert body["details"] == {
        "artifact_id": "text-segmentation",
        "content_hash": artifact_ref["content_hash"],
        "store": "product",
        "version": "1.0.0",
        "release_version": "1.0.0",
        "detail": "Product artifact bytes are missing",
    }


def test_release_list_and_detail_require_current_user_skill_access(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    artifact_ref = store.put(b"private release", artifact_id="private-only")
    store.stage_release(
        "private-only",
        "1.0.0",
        {
            "release_version": "1.0.0",
            "artifact_ref": {
                "artifact_id": artifact_ref.artifact_id,
                "content_hash": artifact_ref.content_hash,
                "manifest_ref": artifact_ref.manifest_ref,
                "store": artifact_ref.store,
            },
            "idempotency_key": "private-only-release",
        },
    )
    store.commit_release("private-only", "1.0.0")

    list_response = client.get("/api/skills/private-only/releases")
    detail_response = client.get("/api/skills/private-only/releases/1.0.0")

    assert list_response.status_code == 404
    assert detail_response.status_code == 404
    assert list_response.json()["error_code"] == "SKILL_NOT_FOUND"
    assert detail_response.json()["error_code"] == "SKILL_NOT_FOUND"


def test_publish_requires_current_user_skill_access_before_reading_committed_release(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    artifact_ref = store.put(b"private release", artifact_id="private-only")
    store.stage_release(
        "private-only",
        "1.0.0",
        {
            "release_version": "1.0.0",
            "artifact_ref": {
                "artifact_id": artifact_ref.artifact_id,
                "content_hash": artifact_ref.content_hash,
                "manifest_ref": artifact_ref.manifest_ref,
                "store": artifact_ref.store,
            },
            "idempotency_key": "publish-idem-private-only-1.0.0",
        },
    )
    store.commit_release("private-only", "1.0.0")
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    get_release_calls: list[tuple[str, str]] = []
    original_get_release = LocalProductArtifactStore.get_release

    def spy_get_release(
        self: LocalProductArtifactStore,
        skill_id: str,
        release_version: str,
    ) -> dict[str, Any] | None:
        get_release_calls.append((skill_id, release_version))
        return original_get_release(self, skill_id, release_version)

    monkeypatch.setattr(LocalProductArtifactStore, "get_release", spy_get_release)

    response = client.post("/api/skills/private-only/publish", json={})

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"
    assert get_release_calls == []
    assert registry.calls == []


def test_publish_success_adds_release_snapshot_to_local_history_without_run_detail(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")
    runs_dir = skill_dir / ".workspace" / "runs"
    run_dir = runs_dir / "run-detail-should-not-drive-history"
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text('{"run_id":"run-detail-should-not-drive-history"}', encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"leak":"nope"}', encoding="utf-8")
    (run_dir / "trace.jsonl").write_text('{"event_type":"trace.leak"}\n', encoding="utf-8")

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})

    assert publish_response.status_code == 200
    extra = publish_response.json()["extra"]
    stage_residual = workspaces_dir / "default" / "releases" / "text-segmentation" / "9.9.9.stage"
    stage_residual.write_text(
        '{"release_version":"9.9.9","artifact_ref":{"artifact_id":"stage-only"}}',
        encoding="utf-8",
    )
    shutil.rmtree(runs_dir)

    history_response = client.get("/api/skills/text-segmentation/history")

    assert history_response.status_code == 200
    history = history_response.json()
    release_items = [item for item in history if item["kind"] == "release"]
    assert len(release_items) == 1
    [snapshot] = release_items
    assert snapshot["release_version"] == "1.0.0"
    assert snapshot["artifact_id"] == extra["artifact_ref"]["artifact_id"]
    assert snapshot["content_hash"] == extra["content_hash"]
    assert snapshot["manifest_ref"] == extra["manifest_ref"]
    assert snapshot["message"].startswith("release-1.0.0")
    assert snapshot["source"] == "git"
    assert snapshot["revertable"] is True
    forbidden_run_detail_fields = {
        "run_id",
        "trace",
        "trace_events",
        "events",
        "final_state",
        "metrics",
        "batch_summary",
        "BatchSummary",
        "RunDetail",
    }
    assert forbidden_run_detail_fields.isdisjoint(snapshot)
    assert {item.get("release_version") for item in history} == {"1.0.0", None}


def test_publish_history_shows_release_snapshot_without_git_repository(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    shutil.rmtree(skill_dir / ".git", ignore_errors=True)

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})

    assert publish_response.status_code == 200
    extra = publish_response.json()["extra"]
    history_response = client.get("/api/skills/text-segmentation/history")

    assert history_response.status_code == 200
    release_items = [item for item in history_response.json() if item["kind"] == "release"]
    assert len(release_items) == 1
    [snapshot] = release_items
    assert snapshot["release_version"] == "1.0.0"
    assert snapshot["artifact_id"] == extra["artifact_ref"]["artifact_id"]
    assert snapshot["content_hash"] == extra["content_hash"]
    assert snapshot["manifest_ref"] == extra["manifest_ref"]
    assert snapshot["source"] == "manifest"
    assert snapshot["revertable"] is False


def test_publish_history_orders_release_snapshots_newest_first_without_git_repository(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    shutil.rmtree(skills_dir / "text-segmentation" / ".git", ignore_errors=True)

    first = client.post("/api/skills/text-segmentation/publish", json={"version": "1.0.0"})
    second = client.post("/api/skills/text-segmentation/publish", json={"version": "2.0.0"})

    assert first.status_code == 200
    assert second.status_code == 200
    history_response = client.get("/api/skills/text-segmentation/history")

    assert history_response.status_code == 200
    release_items = [item for item in history_response.json() if item["kind"] == "release"]
    assert [item["release_version"] for item in release_items] == ["2.0.0", "1.0.0"]
    assert all(not item["timestamp"].startswith("1970-01-01") for item in release_items)


def test_publish_history_shows_release_snapshot_when_release_git_commit_fails(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")

    def fail_release_commit(*_args: object, **_kwargs: object) -> None:
        raise GitCommandError(
            GitCommandResult(
                args=("commit",),
                cwd=skill_dir,
                returncode=128,
                stdout="",
                stderr="commit failed",
            )
        )

    monkeypatch.setattr("app.routers.skills.git_service.commit_empty_snapshot", fail_release_commit)

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})

    assert publish_response.status_code == 200
    extra = publish_response.json()["extra"]
    history_response = client.get("/api/skills/text-segmentation/history")

    assert history_response.status_code == 200
    release_items = [item for item in history_response.json() if item["kind"] == "release"]
    assert len(release_items) == 1
    [snapshot] = release_items
    assert snapshot["release_version"] == "1.0.0"
    assert snapshot["artifact_id"] == extra["artifact_ref"]["artifact_id"]
    assert snapshot["content_hash"] == extra["content_hash"]
    assert snapshot["manifest_ref"] == extra["manifest_ref"]
    assert snapshot["source"] == "manifest"
    assert snapshot["revertable"] is False


def test_publish_history_orders_release_snapshots_newest_first_when_release_git_commit_fails(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")

    def fail_release_commit(*_args: object, **_kwargs: object) -> None:
        raise GitCommandError(
            GitCommandResult(
                args=("commit",),
                cwd=skill_dir,
                returncode=128,
                stdout="",
                stderr="commit failed",
            )
        )

    monkeypatch.setattr("app.routers.skills.git_service.commit_empty_snapshot", fail_release_commit)

    first = client.post("/api/skills/text-segmentation/publish", json={"version": "1.0.0"})
    second = client.post("/api/skills/text-segmentation/publish", json={"version": "2.0.0"})

    assert first.status_code == 200
    assert second.status_code == 200
    history_response = client.get("/api/skills/text-segmentation/history")

    assert history_response.status_code == 200
    release_items = [item for item in history_response.json() if item["kind"] == "release"]
    assert [item["release_version"] for item in release_items] == ["2.0.0", "1.0.0"]
    assert all(not item["timestamp"].startswith("1970-01-01") for item in release_items)


def test_deleting_run_keeps_published_release_snapshot_visible_in_local_history(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    run_dir = skill_dir / ".workspace" / "runs" / "delete-me"

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})
    assert publish_response.status_code == 200
    before_history_response = client.get("/api/skills/text-segmentation/history")
    assert before_history_response.status_code == 200
    before_snapshot = _single_release_snapshot(before_history_response.json())
    before_identity = _release_snapshot_identity(before_snapshot)

    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": "delete-me",
                "status": "success",
                "started_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    delete_response = client.delete("/api/skills/text-segmentation/runs/delete-me")
    after_history_response = client.get("/api/skills/text-segmentation/history")

    assert delete_response.status_code == 204
    assert not run_dir.exists()
    assert after_history_response.status_code == 200
    after_snapshot = _single_release_snapshot(after_history_response.json())
    assert _release_snapshot_identity(after_snapshot) == before_identity


def test_publish_idempotency_retry_does_not_duplicate_release_history_snapshot(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")
    headers = {"Idempotency-Key": "release-click-123"}

    first = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)
    first_history_response = client.get("/api/skills/text-segmentation/history")
    first_marker_count = _release_marker_commit_count(skill_dir, "1.0.0")

    assert first.status_code == 200
    assert first_history_response.status_code == 200
    first_snapshot = _single_release_snapshot(first_history_response.json())
    first_identity = _release_snapshot_identity(first_snapshot)
    assert first_marker_count == 1

    retry = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)
    retry_history_response = client.get("/api/skills/text-segmentation/history")
    retry_marker_count = _release_marker_commit_count(skill_dir, "1.0.0")

    assert retry.status_code == 200
    assert retry_history_response.status_code == 200
    retry_snapshot = _single_release_snapshot(retry_history_response.json())
    assert _release_snapshot_identity(retry_snapshot) == first_identity
    assert retry_marker_count == first_marker_count


def test_publish_idempotency_retry_finds_release_marker_beyond_default_history_window(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")
    headers = {"Idempotency-Key": "release-click-123"}

    first = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)
    assert first.status_code == 200
    assert _release_marker_commit_count(skill_dir, "1.0.0") == 1
    for index in range(101):
        run_git(skill_dir, "commit", "--allow-empty", "-m", f"manual-padding-{index}")

    retry = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)

    assert retry.status_code == 200
    assert _release_marker_commit_count(skill_dir, "1.0.0") == 1


def test_publish_release_marker_commit_preserves_existing_staged_changes(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")
    staged_path = "USER_NOTES.md"
    (skill_dir / staged_path).write_text("draft user note\n", encoding="utf-8")
    run_git(skill_dir, "add", staged_path)

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200
    marker_sha = _release_marker_sha(skill_dir, "1.0.0")
    marker_changed_files = run_git(
        skill_dir,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        marker_sha,
    ).stdout.splitlines()
    staged_files = run_git(skill_dir, "diff", "--cached", "--name-only").stdout.splitlines()
    assert marker_changed_files == []
    assert staged_files == [staged_path]


def test_publish_history_treats_release_prefixed_extra_words_as_regular_git_history(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")
    run_git(skill_dir, "commit", "--allow-empty", "-m", "release-1.0.0 notes")

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})
    history_response = client.get("/api/skills/text-segmentation/history")

    assert publish_response.status_code == 200
    assert history_response.status_code == 200
    release_items = [item for item in history_response.json() if item["kind"] == "release"]
    assert len(release_items) == 1
    [prefixed_commit] = [
        item for item in history_response.json() if item["message"] == "release-1.0.0 notes"
    ]
    assert prefixed_commit["kind"] == "other"
    assert prefixed_commit["release_version"] is None


def test_publish_history_does_not_treat_non_empty_same_subject_commit_as_release_marker(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    skill_dir = skills_dir / "text-segmentation"
    initialize_skill_repository(skill_dir, user_id="alice")
    (skill_dir / "RELEASE_NOTES.md").write_text("user authored release notes\n", encoding="utf-8")
    run_git(skill_dir, "add", "RELEASE_NOTES.md")
    run_git(skill_dir, "commit", "-m", "release-1.0.0")
    ordinary_sha = run_git(skill_dir, "rev-parse", "HEAD").stdout.strip()

    publish_response = client.post("/api/skills/text-segmentation/publish", json={})
    history_response = client.get("/api/skills/text-segmentation/history")

    assert publish_response.status_code == 200
    assert _release_marker_commit_count(skill_dir, "1.0.0") == 2
    marker_sha = _release_marker_sha(skill_dir, "1.0.0")
    marker_body = run_git(skill_dir, "show", "-s", "--format=%B", marker_sha).stdout
    assert marker_sha != ordinary_sha
    assert "Studio-Release-Marker: true" in marker_body
    assert history_response.status_code == 200
    history = history_response.json()
    [release_item] = [item for item in history if item["kind"] == "release"]
    assert release_item["sha"] == marker_sha
    assert release_item["source"] == "git"
    assert release_item["revertable"] is True
    [ordinary_item] = [item for item in history if item["sha"] == ordinary_sha]
    assert ordinary_item["kind"] == "other"
    assert ordinary_item["source"] == "git"
    assert ordinary_item["release_version"] is None


def test_publish_history_standardizes_invalid_release_manifest_error(
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    release_dir = workspaces_dir / "default" / "releases" / "text-segmentation"
    release_dir.mkdir(parents=True)
    (release_dir / "1.0.0.json").write_text("{not-json", encoding="utf-8")

    with TestClient(create_app(), raise_server_exceptions=False) as local_client:
        local_client.headers["Authorization"] = "Bearer studio-test-token"
        response = local_client.get("/api/skills/text-segmentation/history")

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "RELEASE_INVALID_MANIFEST"
    assert body["details"] == {"skill_id": "text-segmentation", "release_version": "1.0.0"}


def test_publish_skill_registry_api_error_returns_local_release_with_remote_sync_warning(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(error=ArtifactRegistryApiError(status_code=401, body="unauthorized"))
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Published to local product store; registry sync failed"
    assert body["artifact_id"] == "text-segmentation"
    assert body["extra"]["release_version"] == "1.0.0"
    assert body["extra"]["artifact_ref"]["artifact_id"] == "text-segmentation"
    assert body["extra"]["content_hash"].startswith("sha256:")
    assert body["extra"]["manifest_ref"] == body["extra"]["artifact_ref"]["manifest_ref"]
    assert body["extra"]["remote_sync"]["status"] == "failed"
    assert body["extra"]["remote_sync"]["error_type"] == "ArtifactRegistryApiError"
    assert body["extra"]["remote_sync"]["details"] == {"status_code": 401, "body": "unauthorized"}
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    assert store.has_release("text-segmentation", "1.0.0")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
    assert release["remote_sync"]["status"] == "failed"
    assert release["remote_sync"]["error_type"] == "ArtifactRegistryApiError"


def test_publish_skill_registry_2xx_invalid_json_returns_local_release_with_remote_sync_warning(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = ArtifactRegistryClient(
        host="https://registry.example.test",
        token="registry-token",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    text="<html>ok</html>",
                    headers={"Content-Type": "text/html"},
                )
            )
        ),
    )
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Published to local product store; registry sync failed"
    assert body["artifact_id"] == "text-segmentation"
    assert body["extra"]["release_version"] == "1.0.0"
    assert body["extra"]["remote_sync"]["status"] == "failed"
    assert body["extra"]["remote_sync"]["error_type"] == "ArtifactRegistryApiError"
    assert body["extra"]["remote_sync"]["details"] == {
        "status_code": 200,
        "body": "<html>ok</html>",
    }
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    assert store.has_release("text-segmentation", "1.0.0")


def test_publish_skill_retries_registry_sync_for_existing_idempotent_release(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(errors=[ArtifactRegistryApiError(status_code=503, body="registry unavailable"), None])
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    first = client.post("/api/skills/text-segmentation/publish", json={})
    retry = client.post("/api/skills/text-segmentation/publish", json={})

    assert first.status_code == 200
    assert first.json()["message"] == "Published to local product store; registry sync failed"
    assert retry.status_code == 200
    body = retry.json()
    assert body["message"] == "Published to registry"
    assert body["artifact_id"] == "text-segmentation"
    assert body["extra"]["remote_sync"] == {"status": "succeeded"}
    assert body["extra"]["registry_artifact_id"] == "art-123"
    assert len(registry.calls) == 2
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
    assert release["remote_sync"] == {"status": "succeeded"}
    raw_release = studio_roots[1] / "default" / "releases" / "text-segmentation" / "1.0.0.json"
    assert "remote_sync" not in raw_release.read_text(encoding="utf-8")


def test_publish_skill_idempotency_key_header_retry_returns_same_release(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    headers = {"Idempotency-Key": "release-click-123"}
    first = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)
    retry = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json()["extra"]["artifact_ref"] == first.json()["extra"]["artifact_ref"]
    assert retry.json()["extra"]["release_version"] == "1.0.0"
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
    assert release["idempotency_key"] == "release-click-123"
    assert registry.calls == []


def test_publish_skill_different_idempotency_key_same_version_returns_conflict_details(
    client: TestClient,
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    first = client.post(
        "/api/skills/text-segmentation/publish",
        json={},
        headers={"Idempotency-Key": "release-click-123"},
    )
    conflict = client.post(
        "/api/skills/text-segmentation/publish",
        json={},
        headers={"Idempotency-Key": "release-click-456"},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error_code"] == "PUBLISH_CONFLICT"
    assert body["details"]["release_version"] == "1.0.0"
    assert body["details"]["existing"]["artifact_id"] == first.json()["artifact_id"]
    assert body["details"]["existing"]["content_hash"] == first.json()["extra"]["content_hash"]
    assert body["details"]["request"]["idempotency_key"] == "release-click-456"
    assert registry.calls == []


def test_publish_skill_same_idempotency_key_recompiles_current_artifact_before_retry(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    first_artifact = _artifact_ref("artifact-1", "a")
    second_artifact = _artifact_ref("artifact-2", "b")
    adapter = FakeCompileAdapter([first_artifact, second_artifact])
    monkeypatch.setattr("app.core.adapters.transport_factory.build_engine_adapter", lambda: adapter)

    headers = {"Idempotency-Key": "release-click-123"}
    first = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)
    conflict = client.post("/api/skills/text-segmentation/publish", json={}, headers=headers)

    assert first.status_code == 200
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error_code"] == "PUBLISH_CONFLICT"
    assert body["details"]["existing"]["artifact_id"] == "artifact-1"
    assert body["details"]["existing"]["content_hash"] == first_artifact["content_hash"]
    assert body["details"]["request"]["artifact_id"] == "artifact-2"
    assert body["details"]["request"]["content_hash"] == second_artifact["content_hash"]
    assert body["details"]["request"]["idempotency_key"] == "release-click-123"
    assert adapter.compile_calls == 2
    assert registry.calls == []


def test_publish_skill_conflict_details_request_uses_current_compiled_artifact(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    first_artifact = _artifact_ref("artifact-1", "a")
    second_artifact = _artifact_ref("artifact-2", "b")
    adapter = FakeCompileAdapter([first_artifact, second_artifact])
    monkeypatch.setattr("app.core.adapters.transport_factory.build_engine_adapter", lambda: adapter)

    first = client.post(
        "/api/skills/text-segmentation/publish",
        json={},
        headers={"Idempotency-Key": "release-click-123"},
    )
    conflict = client.post(
        "/api/skills/text-segmentation/publish",
        json={},
        headers={"Idempotency-Key": "release-click-456"},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error_code"] == "PUBLISH_CONFLICT"
    assert body["details"]["existing"]["artifact_id"] == "artifact-1"
    assert body["details"]["existing"]["content_hash"] == first_artifact["content_hash"]
    assert body["details"]["request"]["artifact_id"] == "artifact-2"
    assert body["details"]["request"]["content_hash"] == second_artifact["content_hash"]
    assert body["details"]["request"]["idempotency_key"] == "release-click-456"
    assert adapter.compile_calls == 2
    assert registry.calls == []


def test_publish_skill_retry_reuses_committed_release_for_owned_skill_when_source_is_missing(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(errors=[ArtifactRegistryApiError(status_code=503, body="registry unavailable"), None])
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")
    create_response = client.post("/api/skills", json={"skill_id": "owned-release", "files": {}})
    assert create_response.status_code == 201
    skill_dir = Path(create_response.json()["directory_path"])

    first = client.post("/api/skills/owned-release/publish", json={})
    shutil.rmtree(skill_dir)
    retry = client.post("/api/skills/owned-release/publish", json={})

    assert first.status_code == 200
    assert first.json()["extra"]["remote_sync"]["status"] == "failed"
    assert retry.status_code == 200
    body = retry.json()
    assert body["message"] == "Published to registry"
    assert body["artifact_id"] == "owned-release"
    assert body["extra"]["remote_sync"] == {"status": "succeeded"}
    assert body["extra"]["registry_artifact_id"] == "art-123"
    assert len(registry.calls) == 2


def test_publish_skill_retry_rejects_source_missing_release_without_current_user_ownership(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    registry = FakeRegistry(errors=[ArtifactRegistryApiError(status_code=503, body="registry unavailable"), None])
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    first = client.post("/api/skills/text-segmentation/publish", json={})
    shutil.rmtree(studio_roots[0] / "text-segmentation")
    retry = client.post("/api/skills/text-segmentation/publish", json={})

    assert first.status_code == 200
    assert first.json()["extra"]["remote_sync"]["status"] == "failed"
    assert retry.status_code == 404
    assert retry.json()["error_code"] == "SKILL_NOT_FOUND"
    assert len(registry.calls) == 1


def test_publish_skill_local_product_blob_error_is_not_reported_as_registry_warning(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    def fail_get(_self: LocalProductArtifactStore, _content_hash: str) -> bytes:
        raise StudioAdapterError("artifact.hash_mismatch", {"expected": "a", "actual": "b"})

    monkeypatch.setattr(LocalProductArtifactStore, "get", fail_get)

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "PUBLISH_FAILED"
    assert "artifact.hash_mismatch" in body["message"]
    assert "remote_sync" not in body.get("details", {})
    assert registry.calls == []
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    assert not store.has_release("text-segmentation", "1.0.0")


def test_publish_skill_partial_failure_response_preserves_compensation_gc_details(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.publish_pipeline import ProductArtifactPublisher, PublishPartialFailure

    registry = FakeRegistry(host="", token="")
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    def fail_publish(
        _self: ProductArtifactPublisher,
        *,
        skill_id: str,
        release_version: str,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
        remote_sync: Any = None,
    ) -> dict[str, Any]:
        raise PublishPartialFailure(
            "rollback cleanup failed",
            {
                "error_code": "release.compensation_gc_failed",
                "phase": "compensation_gc",
                "skill_id": skill_id,
                "release_version": release_version,
                "failed_paths": ["/tmp/releases/text-segmentation/1.0.0.json"],
            },
        )

    monkeypatch.setattr(ProductArtifactPublisher, "publish_release", fail_publish)

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "PUBLISH_FAILED"
    assert body["details"]["phase"] == "compensation_gc"
    assert body["details"]["error_code"] == "release.compensation_gc_failed"
    assert body["details"]["skill_id"] == "text-segmentation"
    assert body["details"]["version"] == "1.0.0"
    assert body["details"]["release_version"] == "1.0.0"
    assert body["details"]["failed_paths"] == ["/tmp/releases/text-segmentation/1.0.0.json"]


def test_publish_skill_registry_network_error_returns_local_release_with_remote_sync_warning(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    request = httpx.Request("POST", "https://registry.example.test/api/v1/artifacts")
    registry = FakeRegistry(error=httpx.ConnectError("DNS failure", request=request))
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Published to local product store; registry sync failed"
    assert body["artifact_id"] == "text-segmentation"
    assert body["extra"]["release_version"] == "1.0.0"
    assert body["extra"]["content_hash"].startswith("sha256:")
    assert body["extra"]["manifest_ref"] == body["extra"]["artifact_ref"]["manifest_ref"]
    assert body["extra"]["remote_sync"]["status"] == "failed"
    assert body["extra"]["remote_sync"]["error_type"] == "ConnectError"
    assert "DNS failure" in body["extra"]["remote_sync"]["error"]
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    assert store.has_release("text-segmentation", "1.0.0")
    release = store.get_release("text-segmentation", "1.0.0")
    assert release is not None
    assert release["remote_sync"]["status"] == "failed"
    assert release["remote_sync"]["error_type"] == "ConnectError"


def test_publish_skill_custom_version(client: TestClient) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={"version": "2.0.0"})

    assert response.status_code == 200
    assert response.json()["extra"]["version"] == "2.0.0"
    assert response.json()["extra"]["release_version"] == "2.0.0"
    assert registry.calls[0]["metadata"]["version"] == "2.0.0"


@pytest.mark.parametrize("version", ["1.0.0 notes", "1.0.0/notes", " 1.0.0", ""])
def test_publish_skill_rejects_marker_unsafe_version(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    version: str,
) -> None:
    registry = FakeRegistry()
    client.app.dependency_overrides[get_registry_client] = lambda: registry
    _write_settings(client, user_id="alice")

    response = client.post("/api/skills/text-segmentation/publish", json={"version": version})

    assert response.status_code == 422
    assert registry.calls == []
    store = LocalProductArtifactStore(root=studio_roots[1] / "default")
    assert store.list_releases("text-segmentation") == []


class FakeRegistry:
    def __init__(
        self,
        *,
        host: str = "https://registry.example.test",
        token: str = "registry-token",
        error: Exception | None = None,
        errors: list[Exception | None] | None = None,
    ) -> None:
        self.host = host
        self.token = token
        self.error = error
        self.errors = list(errors or [])
        self.calls: list[dict[str, Any]] = []

    def upload_artifact(
        self,
        *,
        skill_id: str,
        package: bytes,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"skill_id": skill_id, "package": package, "metadata": metadata})
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        if self.error is not None:
            raise self.error
        return {"artifact_id": "art-123"}

    def sync_release_manifest(
        self,
        *,
        skill_id: str,
        release_manifest: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "skill_id": skill_id,
                "release_manifest": release_manifest,
                "metadata": metadata,
            }
        )
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        if self.error is not None:
            raise self.error
        return {"artifact_id": "art-123"}


class FakeCompileAdapter:
    def __init__(self, artifacts: list[dict[str, Any]]) -> None:
        self._artifacts = list(artifacts)
        self.compile_calls = 0

    def compile(self, _payload: dict[str, Any]) -> dict[str, Any]:
        artifact = self._artifacts[self.compile_calls]
        self.compile_calls += 1
        return dict(artifact)


def _artifact_ref(artifact_id: str, marker: str) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_hash": f"sha256:{marker * 64}",
        "manifest_ref": f"manifests/{artifact_id}.json",
        "store": "product",
    }


def _single_release_snapshot(history: list[dict[str, Any]]) -> dict[str, Any]:
    release_items = [item for item in history if item["kind"] == "release"]
    assert len(release_items) == 1
    return release_items[0]


def _release_snapshot_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: snapshot[key]
        for key in (
            "sha",
            "message",
            "timestamp",
            "kind",
            "release_version",
            "artifact_id",
            "content_hash",
            "manifest_ref",
        )
    }


def _release_marker_commit_count(skill_dir: Path, release_version: str) -> int:
    subject = f"release-{release_version}"
    subjects = run_git(skill_dir, "log", "--format=%s").stdout.splitlines()
    return sum(item == subject for item in subjects)


def _release_marker_sha(skill_dir: Path, release_version: str) -> str:
    subject = f"release-{release_version}"
    rows = run_git(skill_dir, "log", "--format=%H%x1f%s").stdout.splitlines()
    for row in rows:
        sha, _, message = row.partition("\x1f")
        if message == subject:
            return sha
    raise AssertionError(f"missing release marker commit: {subject}")


def _write_settings(client: TestClient, *, user_id: str) -> None:
    response = client.put(
        "/api/settings",
        json={"user_id": user_id, "gitea_host": "https://gitea.example.com"},
    )
    assert response.status_code == 200
