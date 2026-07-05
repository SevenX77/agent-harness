from __future__ import annotations

import hashlib
import importlib
import json
import multiprocessing
import os
import queue
import threading
from pathlib import Path
from typing import Any

import pytest


def test_local_config_store_tracks_user_etag_and_if_match(tmp_path: Path) -> None:
    LocalGatewayConfigStore = _load_symbol(
        "app.core.adapters.gateway_config_store_local",
        "LocalGatewayConfigStore",
    )
    store = LocalGatewayConfigStore(root=tmp_path)

    with pytest.raises(ValueError):
        store.put_config(user_id="", key="llm.roles", value={"roles": {}})

    created = store.put_config(user_id="alice", key="llm.roles", value={"roles": {"writer": {}}})
    first_etag = _etag(created)
    record = store.get_config(user_id="alice", key="llm.roles")

    assert _field(record, "user_id") == "alice"
    assert _field(record, "key") == "llm.roles"
    assert _field(record, "etag") == first_etag
    assert _field(record, "value") == {"roles": {"writer": {}}}

    with pytest.raises(Exception) as exc_info:
        store.put_config(
            user_id="alice",
            key="llm.roles",
            value={"roles": {"critic": {}}},
            if_match="stale-etag",
        )

    assert _error_code(exc_info.value) == "config.etag_conflict"

    updated = store.put_config(
        user_id="alice",
        key="llm.roles",
        value={"roles": {"critic": {}}},
        if_match=first_etag,
    )
    assert _etag(updated) != first_etag


def test_product_artifact_store_get_by_hash_rejects_corrupted_bytes(tmp_path: Path) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = b'{"artifact": "compiled"}'

    artifact_ref = store.put(content=payload, artifact_id="artifact-123")
    content_hash = _field(artifact_ref, "content_hash")

    assert content_hash == f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert store.get(content_hash) == payload

    blob_path = Path(store.blob_path(content_hash))
    blob_path.write_bytes(b"corrupted bytes")

    with pytest.raises(Exception) as exc_info:
        store.get(content_hash)

    assert _error_code(exc_info.value) == "artifact.hash_mismatch"


@pytest.mark.parametrize("content_hash", ["sha256:../../x", "sha256:nothex"])
def test_product_artifact_store_rejects_invalid_content_hash_before_blob_access(
    tmp_path: Path,
    content_hash: str,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    (tmp_path / "blobs").mkdir()
    outside_marker = tmp_path.parent / "x"
    outside_marker.write_bytes(b"outside-root-marker")

    with pytest.raises(Exception) as get_exc:
        store.get(content_hash)

    assert _error_code(get_exc.value) == "artifact.invalid_hash"
    assert outside_marker.read_bytes() == b"outside-root-marker"

    with pytest.raises(Exception) as path_exc:
        store.blob_path(content_hash)

    assert _error_code(path_exc.value) == "artifact.invalid_hash"
    assert outside_marker.read_bytes() == b"outside-root-marker"


def test_product_artifact_store_get_release_returns_version_manifest(tmp_path: Path) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = {
        "release_version": "2026.06.11",
        "idempotency_key": "idem-1",
        "skill_dir": "/tmp/source/text-segmentation",
        "package_bytes": "base64-source-archive",
        "artifact_ref": {
            "artifact_id": "artifact-1",
            "content_hash": f"sha256:{'a' * 64}",
            "manifest_ref": "manifests/artifact-1.json",
            "store": "run",
        },
    }

    store.stage_release("text-segmentation", "2026.06.11", payload)

    assert store.get_release("text-segmentation", "2026.06.11") is None

    store.commit_release("text-segmentation", "2026.06.11")

    manifest = store.get_release("text-segmentation", "2026.06.11")

    assert manifest is not None
    assert manifest["release_version"] == "2026.06.11"
    assert manifest["artifact_id"] == "artifact-1"
    assert manifest["content_hash"] == f"sha256:{'a' * 64}"
    assert manifest["manifest_ref"] == "manifests/artifact-1.json"
    assert manifest["idempotency_key"] == "idem-1"
    assert manifest["artifact_ref"] == {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
        "store": "product",
    }
    _assert_release_manifest_has_no_source_leaks(manifest)


def test_product_artifact_store_concurrent_publish_same_version_never_overwrites_visible_release(
    tmp_path: Path,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payloads = [
        _release_payload("2026.06.11"),
        {
            "release_version": "2026.06.11",
            "idempotency_key": "idem-2",
            "artifact_ref": {
                "artifact_id": "artifact-2",
                "content_hash": f"sha256:{'b' * 64}",
                "manifest_ref": "manifests/artifact-2.json",
                "store": "product",
            },
        },
    ]
    barrier = threading.Barrier(2)
    results: list[tuple[str, str | None]] = []
    results_lock = threading.Lock()

    def publish(payload: dict[str, Any]) -> None:
        barrier.wait(timeout=5)
        try:
            store.stage_release("text-segmentation", "2026.06.11", payload)
            store.commit_release("text-segmentation", "2026.06.11")
        except Exception as exc:
            with results_lock:
                results.append(("conflict", _error_code(exc)))
            return
        with results_lock:
            results.append(("ok", payload["artifact_ref"]["artifact_id"]))

    threads = [threading.Thread(target=publish, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 2
    assert [status for status, _ in results].count("ok") == 1
    assert [status for status, _ in results].count("conflict") == 1
    assert any(error_code == "release.conflict" for status, error_code in results if status == "conflict")
    releases = list((tmp_path / "releases" / "text-segmentation").glob("2026.06.11.json"))
    assert len(releases) == 1
    manifest = store.get_release("text-segmentation", "2026.06.11")
    assert manifest is not None
    winning_artifact = next(value for status, value in results if status == "ok")
    assert manifest["artifact_id"] == winning_artifact
    assert manifest["idempotency_key"] in {"idem-1", "idem-2"}
    assert not list((tmp_path / "releases" / "text-segmentation").glob("2026.06.11*.stage"))


def test_product_artifact_store_lists_releases_with_version_manifest(tmp_path: Path) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)

    first_payload = {
        "release_version": "2026.06.10",
        "idempotency_key": "idem-1",
        "skill_dir": "/tmp/skills/text-segmentation",
        "source_path": "/tmp/skills/text-segmentation/GRAPH.md",
        "artifact_ref": {
            "artifact_id": "artifact-1",
            "content_hash": f"sha256:{'1' * 64}",
            "manifest_ref": "manifests/artifact-1.json",
            "store": "product",
        },
    }
    second_payload = {
        "release_version": "2026.06.11",
        "idempotency_key": "idem-2",
        "package_bytes": "not-a-release-field",
        "artifact_ref": {
            "artifact_id": "artifact-2",
            "content_hash": f"sha256:{'2' * 64}",
            "manifest_ref": "manifests/artifact-2.json",
            "store": "run",
        },
    }

    store.stage_release("text-segmentation", "2026.06.10", first_payload)
    store.stage_release("text-segmentation", "2026.06.11", second_payload)

    assert store.get_release("text-segmentation", "2026.06.10") is None
    assert store.get_release("text-segmentation", "2026.06.11") is None
    assert store.list_releases("text-segmentation") == []

    store.commit_release("text-segmentation", "2026.06.11")
    store.rollback_release("text-segmentation", "2026.06.10")
    (tmp_path / "releases" / "text-segmentation" / "2026.06.12.stage").write_text(
        json.dumps({"release_version": "2026.06.12", "artifact_ref": {"artifact_id": "stale"}}),
        encoding="utf-8",
    )

    assert store.get_release("text-segmentation", "2026.06.10") is None
    releases = store.list_releases("text-segmentation")

    assert [release["release_version"] for release in releases] == ["2026.06.11"]
    [manifest] = releases
    assert manifest["artifact_id"] == "artifact-2"
    assert manifest["content_hash"] == f"sha256:{'2' * 64}"
    assert manifest["manifest_ref"] == "manifests/artifact-2.json"
    assert manifest["artifact_ref"]["store"] == "product"
    assert manifest["idempotency_key"] == "idem-2"
    _assert_release_manifest_has_no_source_leaks(manifest)


def test_product_artifact_store_cleanup_deletes_only_stale_invisible_stage(
    tmp_path: Path,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = _release_payload("v1")

    store.stage_release("text-segmentation", "v1", payload)
    stage_path = tmp_path / "releases" / "text-segmentation" / "v1.stage"
    os.utime(stage_path, (1_000, 1_000))

    assert store.get_release("text-segmentation", "v1") is None
    assert store.list_releases("text-segmentation") == []

    report = store.cleanup_staged_releases(
        "text-segmentation",
        max_age_seconds=60,
        now=1_120,
    )

    assert report["failed"] == []
    assert len(report["cleaned"]) == 1
    assert report["cleaned"][0]["skill_id"] == "text-segmentation"
    assert report["cleaned"][0]["release_version"] == "v1"
    assert report["cleaned"][0]["phase"] == "compensation_gc"
    assert not stage_path.exists()
    assert store.get_release("text-segmentation", "v1") is None
    assert store.list_releases("text-segmentation") == []


def test_product_artifact_store_cleanup_respects_stage_age_bound(tmp_path: Path) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    store.stage_release("text-segmentation", "v1", _release_payload("v1"))
    stage_path = tmp_path / "releases" / "text-segmentation" / "v1.stage"
    os.utime(stage_path, (1_000, 1_000))

    fresh_report = store.cleanup_staged_releases(
        "text-segmentation",
        max_age_seconds=60,
        now=1_059,
    )

    assert fresh_report == {"cleaned": [], "failed": []}
    assert stage_path.exists()

    stale_report = store.cleanup_staged_releases(
        "text-segmentation",
        max_age_seconds=60,
        now=1_061,
    )

    assert stale_report["failed"] == []
    assert [item["release_version"] for item in stale_report["cleaned"]] == ["v1"]
    assert not stage_path.exists()


def test_product_artifact_store_cleanup_corrupted_stage_never_promotes_release(
    tmp_path: Path,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    release_dir = tmp_path / "releases" / "text-segmentation"
    release_dir.mkdir(parents=True)
    stage_path = release_dir / "v1.stage"
    stage_path.write_text("{ not json", encoding="utf-8")
    os.utime(stage_path, (1_000, 1_000))

    report = store.cleanup_staged_releases(
        "text-segmentation",
        max_age_seconds=60,
        now=1_120,
    )

    assert report["failed"] == []
    assert [item["release_version"] for item in report["cleaned"]] == ["v1"]
    assert not stage_path.exists()
    assert not (release_dir / "v1.json").exists()
    assert store.get_release("text-segmentation", "v1") is None
    assert store.list_releases("text-segmentation") == []


def test_product_artifact_store_cleanup_reports_compensation_gc_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    store.stage_release("text-segmentation", "v1", _release_payload("v1"))
    stage_path = tmp_path / "releases" / "text-segmentation" / "v1.stage"
    os.utime(stage_path, (1_000, 1_000))
    original_unlink = Path.unlink

    def fail_stage_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self == stage_path:
            raise PermissionError("stage file is locked")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_stage_unlink)

    report = store.cleanup_staged_releases(
        "text-segmentation",
        max_age_seconds=60,
        now=1_120,
    )

    assert report["cleaned"] == []
    assert len(report["failed"]) == 1
    assert report["failed"][0]["error_code"] == "release.compensation_gc_failed"
    assert report["failed"][0]["phase"] == "compensation_gc"
    assert report["failed"][0]["skill_id"] == "text-segmentation"
    assert report["failed"][0]["release_version"] == "v1"
    assert stage_path.exists()
    assert store.get_release("text-segmentation", "v1") is None


def test_product_artifact_store_rollback_reports_compensation_gc_failure_for_visible_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    store.stage_release("text-segmentation", "v1", _release_payload("v1"))
    store.commit_release("text-segmentation", "v1")
    release_path = tmp_path / "releases" / "text-segmentation" / "v1.json"
    original_unlink = Path.unlink

    def fail_release_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self == release_path:
            raise PermissionError("visible release is locked")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_release_unlink)

    with pytest.raises(Exception) as exc_info:
        store.rollback_release("text-segmentation", "v1")

    assert _error_code(exc_info.value) == "release.compensation_gc_failed"
    assert _field(exc_info.value.error_payload, "phase") == "compensation_gc"
    assert _field(exc_info.value.error_payload, "skill_id") == "text-segmentation"
    assert _field(exc_info.value.error_payload, "release_version") == "v1"
    assert str(release_path) in _field(exc_info.value.error_payload, "failed_paths")
    assert release_path.exists()


def test_product_artifact_store_persists_remote_sync_state_outside_release_manifest(
    tmp_path: Path,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = _release_payload("v1")

    store.stage_release("text-segmentation", "v1", payload)
    store.commit_release("text-segmentation", "v1")
    store.record_remote_sync_state(
        "text-segmentation",
        "v1",
        {
            "status": "failed",
            "error_type": "ArtifactRegistryApiError",
            "error": "registry unavailable",
        },
    )

    raw_manifest = json.loads((tmp_path / "releases" / "text-segmentation" / "v1.json").read_text(encoding="utf-8"))
    assert "remote_sync" not in raw_manifest

    release = store.get_release("text-segmentation", "v1")
    assert release is not None
    assert release["remote_sync"] == {
        "status": "failed",
        "error_type": "ArtifactRegistryApiError",
        "error": "registry unavailable",
    }
    assert store.list_releases("text-segmentation")[0]["remote_sync"]["status"] == "failed"

    store.record_remote_sync_state("text-segmentation", "v1", {"status": "succeeded"})

    retry_release = store.get_release("text-segmentation", "v1")
    assert retry_release is not None
    assert retry_release["remote_sync"] == {"status": "succeeded"}
    assert retry_release["artifact_ref"] == release["artifact_ref"]


def test_product_artifact_store_rejects_mismatched_release_version_payload(
    tmp_path: Path,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = _release_payload(release_version="v2")

    with pytest.raises(Exception) as exc_info:
        store.stage_release("text-segmentation", "v1", payload)

    assert _error_code(exc_info.value) == "release.invalid_manifest"
    assert _field(exc_info.value.error_payload, "skill_id") == "text-segmentation"
    assert _field(exc_info.value.error_payload, "release_version") == "v1"
    assert _field(exc_info.value.error_payload, "field") == "release_version"
    assert not (tmp_path / "releases" / "text-segmentation" / "v1.stage").exists()


@pytest.mark.parametrize("content_hash", ["sha256:nothex", f"sha256:{'g' * 64}", "not-sha"])
def test_product_artifact_store_rejects_invalid_release_content_hash(
    tmp_path: Path,
    content_hash: str,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = _release_payload("v1")
    payload["artifact_ref"]["content_hash"] = content_hash

    with pytest.raises(Exception) as stage_exc:
        store.stage_release("text-segmentation", "v1", payload)

    assert _error_code(stage_exc.value) == "release.invalid_manifest"
    assert _field(stage_exc.value.error_payload, "field") == "content_hash"
    assert not (tmp_path / "releases" / "text-segmentation" / "v1.stage").exists()

    release_dir = tmp_path / "releases" / "text-segmentation"
    release_dir.mkdir(parents=True)
    (release_dir / "v1.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(Exception) as get_exc:
        store.get_release("text-segmentation", "v1")

    assert _error_code(get_exc.value) == "release.invalid_manifest"
    assert _field(get_exc.value.error_payload, "field") == "content_hash"


def test_product_artifact_store_accepts_valid_release_content_hash(tmp_path: Path) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = _release_payload("v1")
    payload["artifact_ref"]["content_hash"] = f"sha256:{'A' * 64}"

    store.stage_release("text-segmentation", "v1", payload)
    store.commit_release("text-segmentation", "v1")

    manifest = store.get_release("text-segmentation", "v1")

    assert manifest is not None
    assert manifest["content_hash"] == f"sha256:{'a' * 64}"
    assert manifest["artifact_ref"]["content_hash"] == f"sha256:{'a' * 64}"


@pytest.mark.parametrize(
    ("operation", "skill_id", "release_version"),
    [
        ("stage", "../outside", "v1"),
        ("stage", "text-segmentation", "../outside"),
        ("get", "../outside", "v1"),
        ("get", "text-segmentation", "../outside"),
        ("list", "../outside", None),
        ("commit", "../outside", "v1"),
        ("commit", "text-segmentation", "../outside"),
        ("rollback", "../outside", "v1"),
        ("rollback", "text-segmentation", "../outside"),
    ],
)
def test_product_artifact_store_rejects_release_path_escape(
    tmp_path: Path,
    operation: str,
    skill_id: str,
    release_version: str | None,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)

    with pytest.raises(Exception) as exc_info:
        if operation == "stage":
            assert release_version is not None
            store.stage_release(skill_id, release_version, _release_payload(release_version))
        elif operation == "get":
            assert release_version is not None
            store.get_release(skill_id, release_version)
        elif operation == "list":
            store.list_releases(skill_id)
        elif operation == "commit":
            assert release_version is not None
            store.commit_release(skill_id, release_version)
        elif operation == "rollback":
            assert release_version is not None
            store.rollback_release(skill_id, release_version)
        else:
            pytest.fail(f"Unhandled release operation {operation}")

    assert _error_code(exc_info.value) == "release.invalid_path"
    assert not any(tmp_path.rglob("*outside*"))
    assert not (tmp_path.parent / "outside").exists()


def test_product_artifact_store_reports_corrupted_release_manifest(
    tmp_path: Path,
) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    release_dir = tmp_path / "releases" / "text-segmentation"
    release_dir.mkdir(parents=True)
    (release_dir / "v1.json").write_text("{ not json", encoding="utf-8")

    with pytest.raises(Exception) as exc_info:
        store.get_release("text-segmentation", "v1")

    assert _error_code(exc_info.value) == "release.invalid_manifest"
    assert _field(exc_info.value.error_payload, "skill_id") == "text-segmentation"
    assert _field(exc_info.value.error_payload, "release_version") == "v1"


def test_runtime_state_store_rejects_missing_lease_and_stale_fencing_token(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    with pytest.raises(Exception) as exc_info:
        store.snapshot(run_id="run-123", state={"phase": "setup"}, lease=None)
    assert _error_code(exc_info.value) == "state.lease_required"

    stale_lease = store.acquire_lease(run_id="run-123", owner_id="worker-a", ttl_ms=0)
    current_lease = store.acquire_lease(run_id="run-123", owner_id="worker-b", ttl_ms=30_000)

    with pytest.raises(Exception) as exc_info:
        store.snapshot(run_id="run-123", state={"phase": "stale"}, lease=stale_lease)
    assert _error_code(exc_info.value) == "state.lease_fenced"

    store.snapshot(run_id="run-123", state={"phase": "current"}, lease=current_lease)
    assert _field(store.restore(run_id="run-123"), "state") == {"phase": "current"}


@pytest.mark.parametrize("run_id", ["", ".", "..", "bad/run", "bad\\run", "-bad", "bad run"])
def test_runtime_state_store_rejects_unsafe_run_id_segments(tmp_path: Path, run_id: str) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    with pytest.raises(Exception) as acquire_error:
        store.acquire_lease(run_id=run_id, owner_id="worker-a", ttl_ms=30_000)
    assert _error_code(acquire_error.value) == "state.invalid_run_id"

    with pytest.raises(Exception) as restore_error:
        store.restore(run_id=run_id)
    assert _error_code(restore_error.value) == "state.invalid_run_id"

    assert not (tmp_path.parent / "bad").exists()
    assert not (tmp_path / "runs").exists()


def test_runtime_state_store_rejects_second_owner_while_lease_is_active(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    first_lease = store.acquire_lease(run_id="run-123", owner_id="worker-a", ttl_ms=30_000)

    with pytest.raises(Exception) as exc_info:
        store.acquire_lease(run_id="run-123", owner_id="worker-b", ttl_ms=30_000)

    assert _error_code(exc_info.value) == "state.lease_conflict"
    lease_path = tmp_path / "runs" / "run-123" / "lease.json"
    lease_data = json.loads(lease_path.read_text(encoding="utf-8"))
    assert lease_data["owner_id"] == "worker-a"
    assert lease_data["fencing_token"] == _field(first_lease, "fencing_token")


def test_runtime_state_store_allows_expired_lease_takeover_with_higher_fencing_token(
    tmp_path: Path,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    stale = store.acquire_lease(run_id="run-expired", owner_id="worker-a", ttl_ms=30_000)
    lease_path = tmp_path / "runs" / "run-expired" / "lease.json"
    stale_data = json.loads(lease_path.read_text(encoding="utf-8"))
    stale_data["acquired_at_ms"] = 1
    stale_data["expires_at_ms"] = 1
    lease_path.write_text(json.dumps(stale_data), encoding="utf-8")

    current = store.acquire_lease(run_id="run-expired", owner_id="worker-b", ttl_ms=30_000)

    assert _field(current, "fencing_token") > _field(stale, "fencing_token")
    lease_data = json.loads(lease_path.read_text(encoding="utf-8"))
    assert lease_data["owner_id"] == "worker-b"
    assert lease_data["fencing_token"] == _field(current, "fencing_token")


def test_runtime_state_store_rejects_reacquire_for_active_owner_and_uses_heartbeat(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    first_lease = store.acquire_lease(run_id="run-renew", owner_id="worker-a", ttl_ms=30_000)

    with pytest.raises(Exception) as reacquire:
        store.acquire_lease(run_id="run-renew", owner_id="worker-a", ttl_ms=30_000)
    assert _error_code(reacquire.value) == "state.lease_conflict"

    renewed = store.heartbeat(run_id="run-renew", lease=first_lease)
    assert _field(renewed, "lease_id") == _field(first_lease, "lease_id")
    assert _field(renewed, "fencing_token") == _field(first_lease, "fencing_token")


def test_runtime_state_store_concurrent_first_acquire_allows_only_one_owner(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )

    class CoordinatedRuntimeStateStore(LocalRuntimeStateStore):
        def __init__(self, root: Path) -> None:
            super().__init__(root=root)
            self._entered = 0
            self._entered_lock = threading.Lock()
            self._first_entered = threading.Event()
            self._second_entered = threading.Event()

        def _next_fencing_token(self, run_dir: Path) -> int:
            del run_dir
            with self._entered_lock:
                self._entered += 1
                entered = self._entered
                if entered == 1:
                    self._first_entered.set()
                elif entered == 2:
                    self._second_entered.set()
            if entered == 1:
                self._second_entered.wait(timeout=0.2)
            return entered

    store = CoordinatedRuntimeStateStore(root=tmp_path)
    results: dict[str, str] = {}

    def acquire(owner_id: str) -> None:
        try:
            lease = store.acquire_lease(run_id="run-race", owner_id=owner_id, ttl_ms=30_000)
            results[owner_id] = f"ok:{_field(lease, 'fencing_token')}"
        except Exception as exc:  # noqa: BLE001 - assert typed adapter error below.
            results[owner_id] = f"error:{_error_code(exc)}"

    first = threading.Thread(target=acquire, args=("worker-a",))
    second = threading.Thread(target=acquire, args=("worker-b",))
    first.start()
    assert store._first_entered.wait(timeout=1)
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert sorted(results.values()) == ["error:state.lease_conflict", "ok:1"]

    lease_data = json.loads((tmp_path / "runs" / "run-race" / "lease.json").read_text(encoding="utf-8"))
    winning_owner = next(owner for owner, result in results.items() if result == "ok:1")
    assert lease_data["owner_id"] == winning_owner
    assert lease_data["fencing_token"] == 1


def _reap_processes(processes) -> None:
    """Ensure no spawn-context child outlives its test (terminate -> kill)."""
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)


def _close_ctx_queue(results_queue) -> None:
    """Release a spawn-context Queue's feeder thread before the test returns.

    Feeder threads leaked from ctx.Queue()s across the suite crash the
    interpreter/coverage shutdown (exit 139 AFTER "N passed" on quality-gates,
    teardown-segfault round 2). close() + join_thread() reaps them.
    """
    results_queue.close()
    results_queue.join_thread()


def test_runtime_state_store_multiprocess_first_acquire_allows_only_one_owner(
    tmp_path: Path,
) -> None:
    worker_count = 8
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(worker_count)
    results = ctx.Queue()
    processes = [
        ctx.Process(
            target=_runtime_state_acquire_worker,
            args=(tmp_path, "run-multiprocess-race", f"worker-{index}", barrier, results),
        )
        for index in range(worker_count)
    ]

    try:
        for process in processes:
            process.start()
        for process in processes:
            # 60s, not 10s: a loaded CI runner spawning 8 fresh interpreters (each
            # re-imports the whole backend under the "spawn" context) can legitimately
            # take well over 10s to finish, leaving a still-running worker that trips
            # `assert alive == []`. The processes complete correctly; only the wait
            # was too tight.
            process.join(timeout=60)

        alive = [process.pid for process in processes if process.is_alive()]
        _reap_processes(processes)

        assert alive == []
        assert [process.exitcode for process in processes] == [0] * worker_count

        acquired: list[tuple[str, int]] = []
        errors: list[tuple[str, str | None, str]] = []
        for _ in processes:
            status, owner_id, value, exc_type = results.get(timeout=1)
            if status == "ok":
                acquired.append((owner_id, int(value)))
            else:
                errors.append((owner_id, value, exc_type))

        lease_data = json.loads((tmp_path / "runs" / "run-multiprocess-race" / "lease.json").read_text(encoding="utf-8"))
        assert acquired == [(lease_data["owner_id"], 1)]
        assert len(errors) == worker_count - 1
        assert {error_code for _, error_code, _ in errors} == {"state.lease_conflict"}
        assert {exc_type for _, _, exc_type in errors} == {"StudioAdapterError"}
    finally:
        _reap_processes(processes)
        _close_ctx_queue(results)


def test_runtime_state_store_multiprocess_expired_takeover_allows_only_one_owner(
    tmp_path: Path,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)
    stale = store.acquire_lease(run_id="run-multiprocess-expired", owner_id="worker-stale", ttl_ms=30_000)
    lease_path = tmp_path / "runs" / "run-multiprocess-expired" / "lease.json"
    lease_data = json.loads(lease_path.read_text(encoding="utf-8"))
    lease_data["acquired_at_ms"] = 1
    lease_data["expires_at_ms"] = 1
    lease_path.write_text(json.dumps(lease_data), encoding="utf-8")

    worker_count = 8
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(worker_count)
    results = ctx.Queue()
    processes = [
        ctx.Process(
            target=_runtime_state_slow_expired_takeover_worker,
            args=(
                tmp_path,
                "run-multiprocess-expired",
                f"worker-{index}",
                barrier,
                tmp_path / "race-markers",
                worker_count,
                results,
            ),
        )
        for index in range(worker_count)
    ]

    try:
        for process in processes:
            process.start()
        for process in processes:
            # 60s, not 10s: a loaded CI runner spawning 8 fresh interpreters (each
            # re-imports the whole backend under the "spawn" context) can legitimately
            # take well over 10s to finish, leaving a still-running worker that trips
            # `assert alive == []`. The processes complete correctly; only the wait
            # was too tight.
            process.join(timeout=60)

        alive = [process.pid for process in processes if process.is_alive()]
        _reap_processes(processes)

        assert alive == []
        assert [process.exitcode for process in processes] == [0] * worker_count

        acquired: list[tuple[str, int]] = []
        errors: list[tuple[str, str | None, str]] = []
        for _ in processes:
            status, owner_id, value, exc_type = results.get(timeout=1)
            if status == "ok":
                acquired.append((owner_id, int(value)))
            else:
                errors.append((owner_id, value, exc_type))

        final_lease = json.loads(lease_path.read_text(encoding="utf-8"))
        assert acquired == [(final_lease["owner_id"], stale.fencing_token + 1)]
        assert len(errors) == worker_count - 1
        assert {error_code for _, error_code, _ in errors} == {"state.lease_conflict"}
        assert {exc_type for _, _, exc_type in errors} == {"StudioAdapterError"}
    finally:
        _reap_processes(processes)
        _close_ctx_queue(results)


def test_runtime_state_store_acquire_obeys_cross_process_run_file_lock(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-file-lock"
    run_dir.mkdir(parents=True)
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Queue()
    contender_ready = ctx.Queue()
    release = ctx.Event()
    results = ctx.Queue()
    start_acquire = ctx.Event()
    holder = ctx.Process(target=_runtime_state_file_lock_holder, args=(run_dir, ready, release))
    contender = ctx.Process(
        target=_runtime_state_ready_acquire_worker,
        args=(tmp_path, "run-file-lock", "worker-contender", contender_ready, start_acquire, results),
    )

    try:
        holder.start()
        assert ready.get(timeout=30) == "locked"
        contender.start()
        assert contender_ready.get(timeout=30) == "ready"
        start_acquire.set()

        with pytest.raises(queue.Empty):
            results.get(timeout=0.5)

        release.set()
        holder.join(timeout=30)
        contender.join(timeout=30)

        assert holder.exitcode == 0
        assert contender.exitcode == 0
        assert results.get(timeout=10)[0] == "ok"
    finally:
        # Unblock children before reaping so terminate/kill is the fallback,
        # not the norm; a join(timeout=30) miss must never leak a child into
        # the rest of the suite (teardown-segfault round 2).
        release.set()
        start_acquire.set()
        _reap_processes((holder, contender))
        for ctx_queue in (ready, contender_ready, results):
            _close_ctx_queue(ctx_queue)


def test_runtime_state_store_fencing_token_stays_monotonic_after_release(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    released_lease = store.acquire_lease(run_id="run-123", owner_id="worker-a", ttl_ms=30_000)
    store.release(run_id="run-123", lease=released_lease)
    current_lease = store.acquire_lease(run_id="run-123", owner_id="worker-b", ttl_ms=30_000)

    assert _field(current_lease, "fencing_token") > _field(released_lease, "fencing_token")

    with pytest.raises(Exception) as exc_info:
        store.snapshot(run_id="run-123", state={"phase": "released"}, lease=released_lease)

    assert _error_code(exc_info.value) == "state.lease_fenced"


def test_d10_runtime_state_store_old_fencing_token_cannot_mutate_current_lease_or_snapshot(
    tmp_path: Path,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    stale = store.acquire_lease(run_id="run-d10-fenced", owner_id="worker-a", ttl_ms=0)
    current = store.acquire_lease(run_id="run-d10-fenced", owner_id="worker-b", ttl_ms=30_000)
    store.snapshot(run_id="run-d10-fenced", state={"owner": "worker-b"}, lease=current)

    for operation in ("heartbeat", "snapshot", "release"):
        with pytest.raises(Exception) as exc_info:
            if operation == "heartbeat":
                store.heartbeat(run_id="run-d10-fenced", lease=stale)
            elif operation == "snapshot":
                store.snapshot(run_id="run-d10-fenced", state={"owner": "worker-a"}, lease=stale)
            else:
                store.release(run_id="run-d10-fenced", lease=stale)

        assert _error_code(exc_info.value) == "state.lease_fenced"
        assert _field(exc_info.value.error_payload, "action") == operation

    lease_data = json.loads((tmp_path / "runs" / "run-d10-fenced" / "lease.json").read_text(encoding="utf-8"))
    assert lease_data["owner_id"] == "worker-b"
    assert lease_data["fencing_token"] == _field(current, "fencing_token")
    assert _field(store.restore(run_id="run-d10-fenced"), "state") == {"owner": "worker-b"}


def test_runtime_state_store_release_is_observable_and_stale_safe(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)
    lease_path = tmp_path / "runs" / "run-x" / "lease.json"

    # A stale owner must not release the lease now held by a newer fencing token.
    stale = store.acquire_lease(run_id="run-x", owner_id="worker-a", ttl_ms=0)
    current = store.acquire_lease(run_id="run-x", owner_id="worker-b", ttl_ms=30_000)
    with pytest.raises(Exception) as stale_release:
        store.release(run_id="run-x", lease=stale)
    assert _error_code(stale_release.value) == "state.lease_fenced"
    assert lease_path.exists()

    # A corrupt lease file is fenced and left in place, not silently ignored.
    lease_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(Exception) as corrupt_release:
        store.release(run_id="run-x", lease=current)
    assert _error_code(corrupt_release.value) == "state.lease_fenced"
    assert lease_path.exists()

    # The rightful owner releases its own lease.
    owner = store.acquire_lease(run_id="run-y", owner_id="worker-c", ttl_ms=30_000)
    store.release(run_id="run-y", lease=owner)
    assert not (tmp_path / "runs" / "run-y" / "lease.json").exists()

    with pytest.raises(Exception) as duplicate_release:
        store.release(run_id="run-y", lease=owner)
    assert _error_code(duplicate_release.value) == "state.lease_fenced"


def test_runtime_state_store_release_reports_unlink_failure_and_keeps_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)
    lease = store.acquire_lease(run_id="run-unlink", owner_id="worker-a", ttl_ms=30_000)
    lease_path = tmp_path / "runs" / "run-unlink" / "lease.json"
    original_unlink = Path.unlink

    def fail_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == lease_path:
            raise OSError("disk refused unlink")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(Exception) as exc_info:
        store.release(run_id="run-unlink", lease=lease)

    assert _error_code(exc_info.value) == "state.release_failed"
    assert _field(exc_info.value.error_payload, "run_id") == "run-unlink"
    assert _field(exc_info.value.error_payload, "action") == "release"
    assert lease_path.exists()

    with pytest.raises(Exception) as reacquire:
        store.acquire_lease(run_id="run-unlink", owner_id="worker-b", ttl_ms=30_000)
    assert _error_code(reacquire.value) == "state.lease_conflict"


@pytest.mark.parametrize(
    "checkpointer_spec",
    [
        "memory",
        "postgresql://user:pass@example.invalid/db",
        "sqlite:/tmp/outside-run-checkpoints.db",
        "sqlite:/tmp/runtime-root/runs/other-run/checkpoints.db",
    ],
)
def test_runtime_state_store_rejects_untrusted_checkpointer_specs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpointer_spec: str,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    StateSnapshot = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "StateSnapshot",
    )
    checkpointer_module = importlib.import_module("graph_agent.core.checkpointer")
    resolve_calls: list[str] = []
    monkeypatch.setattr(
        checkpointer_module,
        "resolve_checkpointer",
        lambda spec: resolve_calls.append(spec) or object(),
    )
    store = LocalRuntimeStateStore(root=tmp_path)
    snapshot = StateSnapshot(
        run_id="run-safe",
        state={"checkpointer_spec": checkpointer_spec},
        fencing_token=1,
    )

    with pytest.raises(Exception) as exc_info:
        store.restore_checkpointer(snapshot)

    assert _error_code(exc_info.value) == "state.invalid_checkpointer"
    assert resolve_calls == []


def test_runtime_state_store_accepts_per_run_sqlite_checkpointer_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    StateSnapshot = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "StateSnapshot",
    )
    checkpointer_module = importlib.import_module("graph_agent.core.checkpointer")
    resolved = object()
    resolve_calls: list[str] = []

    def fake_resolve(spec: str) -> object:
        resolve_calls.append(spec)
        return resolved

    monkeypatch.setattr(checkpointer_module, "resolve_checkpointer", fake_resolve)
    store = LocalRuntimeStateStore(root=tmp_path)
    checkpointer_path = tmp_path / "skills" / "demo" / ".workspace" / "runs" / "run-safe" / "checkpoints.db"
    checkpointer_path.parent.mkdir(parents=True)
    checkpointer_path.write_bytes(b"")
    checkpointer_spec = f"sqlite:{checkpointer_path}"
    snapshot = StateSnapshot(
        run_id="run-safe",
        state={"checkpointer_spec": checkpointer_spec},
        fencing_token=1,
    )

    assert store.restore_checkpointer(snapshot) is resolved
    assert resolve_calls == [checkpointer_spec]


def test_runtime_state_store_rejects_missing_per_run_checkpointer_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    StateSnapshot = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "StateSnapshot",
    )
    checkpointer_module = importlib.import_module("graph_agent.core.checkpointer")
    resolve_calls: list[str] = []
    monkeypatch.setattr(
        checkpointer_module,
        "resolve_checkpointer",
        lambda spec: resolve_calls.append(spec) or object(),
    )
    store = LocalRuntimeStateStore(root=tmp_path)
    checkpointer_path = tmp_path / "skills" / "demo" / ".workspace" / "runs" / "run-safe" / "checkpoints.db"
    checkpointer_spec = f"sqlite:{checkpointer_path}"
    snapshot = StateSnapshot(
        run_id="run-safe",
        state={"checkpointer_spec": checkpointer_spec},
        fencing_token=1,
    )

    with pytest.raises(Exception) as exc_info:
        store.restore_checkpointer(snapshot)

    assert _error_code(exc_info.value) == "state.not_found"
    assert resolve_calls == []
    assert not checkpointer_path.exists()


def test_runtime_state_store_rejects_forged_lease_identity(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    LeaseToken = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LeaseToken",
    )
    store = LocalRuntimeStateStore(root=tmp_path)
    active = store.acquire_lease(run_id="run-forged", owner_id="worker-a", ttl_ms=30_000)
    forged_same_token = LeaseToken(
        lease_id="forged-lease",
        owner_id="worker-b",
        fencing_token=_field(active, "fencing_token"),
        ttl_ms=30_000,
    )

    for operation in ("heartbeat", "snapshot", "release"):
        with pytest.raises(Exception) as exc_info:
            if operation == "heartbeat":
                store.heartbeat(run_id="run-forged", lease=forged_same_token)
            elif operation == "snapshot":
                store.snapshot(run_id="run-forged", state={"phase": "forged"}, lease=forged_same_token)
            else:
                store.release(run_id="run-forged", lease=forged_same_token)
        assert _error_code(exc_info.value) == "state.lease_fenced"

    lease_data = json.loads((tmp_path / "runs" / "run-forged" / "lease.json").read_text(encoding="utf-8"))
    assert lease_data["lease_id"] == _field(active, "lease_id")
    assert lease_data["owner_id"] == "worker-a"


def test_run_artifact_store_rejects_writes_after_seal(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)

    store.begin_run(run_id="run-123")
    store.put_batch(
        run_id="run-123",
        objects=[{"path": "trace.jsonl", "content": b'{"seq": 1}\n'}],
    )
    store.seal_run(run_id="run-123")

    with pytest.raises(Exception) as exc_info:
        store.put_batch(
            run_id="run-123",
            objects=[{"path": "trace.jsonl", "content": b'{"seq": 2}\n'}],
        )

    assert _error_code(exc_info.value) == "artifact.sealed_write"


def test_local_run_artifact_store_matches_graph_agent_run_artifact_contract(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)

    store.begin_run("run-123", metadata={"artifact_id": "demo.skill"})
    refs = store.put_batch("run-123", {"outputs.json": b'{"success": true}'})

    ref = refs["outputs.json"] if isinstance(refs, dict) else refs[0]
    assert _field(ref, "bytes_ref")
    assert _field(ref, "content_hash")
    assert _field(ref, "path") == "outputs.json"

    store.seal_run("run-123")

    assert (tmp_path / "runs" / "run-123" / "manifest.json").exists()
    assert not (tmp_path / "runs" / "runs").exists()
    assert store.get_object(hash=_field(ref, "content_hash")) == b'{"success": true}'


def test_run_artifact_store_rejects_begin_run_metadata_update_after_seal(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)

    store.begin_run("sealed-run", metadata={"artifact_id": "demo.skill"})
    store.put_batch("sealed-run", {"outputs.json": b'{"ok": true}'})
    store.seal_run("sealed-run")

    with pytest.raises(Exception) as exc_info:
        store.begin_run("sealed-run", metadata={"artifact_id": "rewritten.skill"})

    assert _error_code(exc_info.value) == "artifact.sealed_write"
    manifest = json.loads((tmp_path / "runs" / "sealed-run" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata"] == {"artifact_id": "demo.skill"}


def test_run_artifact_store_seal_indexes_legacy_files_manifest(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)
    content = b"legacy output"
    sha_val = hashlib.sha256(content).hexdigest()
    run_dir = tmp_path / "runs" / "legacy-run"
    run_dir.mkdir(parents=True)
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / sha_val).write_bytes(content)
    (run_dir / "manifest.json").write_text(
        json.dumps({"files": {"outputs.json": f"sha256:{sha_val}"}}),
        encoding="utf-8",
    )

    index = store.seal_run("legacy-run")

    assert len(_field(index, "objects")) == 1
    [ref] = _field(index, "objects")
    assert _field(ref, "path") == "outputs.json"
    assert _field(ref, "content_hash") == f"sha256:{sha_val}"
    assert _field(ref, "bytes_ref") == f"bytes://sha256:{sha_val}"
    assert _field(ref, "size_bytes") == len(content)


def test_run_artifact_store_get_run_object_rejects_legacy_files_without_object_refs(
    tmp_path: Path,
) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)
    content = b"legacy output"
    sha_val = hashlib.sha256(content).hexdigest()
    run_dir = tmp_path / "runs" / "legacy-read-run"
    run_dir.mkdir(parents=True)
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / sha_val).write_bytes(content)
    (run_dir / "sealed").write_text("sealed", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"files": {"outputs.json": f"sha256:{sha_val}"}}),
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        store.get_run_object("legacy-read-run", "outputs.json")

    assert _error_code(exc_info.value) == "artifact.not_found"


@pytest.mark.parametrize(
    "manifest",
    [
        [],
        {"object_refs": []},
        {"object_refs": {"outputs.json": "sha256:not-an-object-ref"}},
        {"object_refs": {"outputs.json": {"bytes_ref": "bytes://sha256:abc", "path": "outputs.json"}}},
    ],
)
def test_run_artifact_store_get_run_object_wraps_invalid_manifest_shape_as_corrupt(
    tmp_path: Path,
    manifest: Any,
) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)
    run_dir = tmp_path / "runs" / "bad-manifest-run"
    run_dir.mkdir(parents=True)
    (run_dir / "sealed").write_text("sealed", encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(Exception) as exc_info:
        store.get_run_object("bad-manifest-run", "outputs.json")

    assert _error_code(exc_info.value) == "artifact.corrupt_manifest"


@pytest.mark.parametrize(
    "object_ref",
    [
        "sha256:not-an-object-ref",
        {"bytes_ref": "bytes://sha256:abc", "path": "outputs.json"},
    ],
)
def test_run_artifact_store_seal_run_wraps_declared_invalid_object_refs_as_corrupt(
    tmp_path: Path,
    object_ref: Any,
) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)
    run_dir = tmp_path / "runs" / "bad-seal-manifest-run"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "files": {"outputs.json": f"sha256:{'1' * 64}"},
                "object_refs": {"outputs.json": object_ref},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        store.seal_run("bad-seal-manifest-run")

    assert _error_code(exc_info.value) == "artifact.corrupt_manifest"


def test_run_artifact_store_seal_run_does_not_leave_marker_after_invalid_object_refs(
    tmp_path: Path,
) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)
    run_dir = tmp_path / "runs" / "retryable-bad-seal-run"
    run_dir.mkdir(parents=True)
    content = b'{"ok": true}'
    sha_val = hashlib.sha256(content).hexdigest()
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / sha_val).write_bytes(content)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "files": {"outputs.json": f"sha256:{sha_val}"},
                "object_refs": {"outputs.json": "sha256:not-an-object-ref"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        store.seal_run("retryable-bad-seal-run")

    assert _error_code(exc_info.value) == "artifact.corrupt_manifest"
    assert not (run_dir / "sealed").exists()

    (run_dir / "manifest.json").write_text(
        json.dumps({"files": {"outputs.json": f"sha256:{sha_val}"}}),
        encoding="utf-8",
    )
    index = store.seal_run("retryable-bad-seal-run")

    assert (run_dir / "sealed").exists()
    assert _field(index, "sealed") is True


def test_run_artifact_store_rejects_run_id_path_escape(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)

    with pytest.raises(Exception) as exc_info:
        store.begin_run("../outside", metadata={"artifact_id": "demo.skill"})

    assert _error_code(exc_info.value) == "artifact.invalid_run_id"
    assert not (tmp_path / "outside").exists()


def test_run_artifact_store_get_object_rejects_corrupted_blob(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)
    refs = store.put_batch("run-123", {"outputs.json": b"original"})
    ref = refs["outputs.json"] if isinstance(refs, dict) else refs[0]
    sha_val = _field(ref, "content_hash").split(":", 1)[1]
    (tmp_path / "blobs" / sha_val).write_bytes(b"corrupted")

    with pytest.raises(Exception) as exc_info:
        store.get_object(hash=_field(ref, "content_hash"))

    assert _error_code(exc_info.value) == "artifact.hash_mismatch"


def _load_symbol(module_name: str, symbol_name: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"{module_name} is missing for the Studio MVP1 local provider contract: {exc}")
    try:
        return getattr(module, symbol_name)
    except AttributeError:
        pytest.fail(f"{module_name}.{symbol_name} is missing from the Studio MVP1 local provider contract")


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _etag(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "etag"))


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "error_code", None) or getattr(exc, "code", None)


def _runtime_state_acquire_worker(
    root: Path,
    run_id: str,
    owner_id: str,
    barrier: Any,
    results: Any,
) -> None:
    from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore

    store = LocalRuntimeStateStore(root=root)
    barrier.wait(timeout=5)
    try:
        lease = store.acquire_lease(run_id=run_id, owner_id=owner_id, ttl_ms=30_000)
    except Exception as exc:  # noqa: BLE001 - the contract asserts this is the typed adapter error.
        results.put(("error", owner_id, _error_code(exc), type(exc).__name__))
        return
    results.put(("ok", owner_id, lease.fencing_token, ""))


def _runtime_state_slow_expired_takeover_worker(
    root: Path,
    run_id: str,
    owner_id: str,
    barrier: Any,
    race_dir: Path,
    worker_count: int,
    results: Any,
) -> None:
    import os
    import time

    from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore

    class SlowRuntimeStateStore(LocalRuntimeStateStore):
        def _next_fencing_token(self, run_dir: Path) -> int:
            race_dir.mkdir(parents=True, exist_ok=True)
            (race_dir / f"{os.getpid()}.entered").write_text(owner_id, encoding="utf-8")
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                if len(list(race_dir.glob("*.entered"))) >= min(worker_count, 2):
                    break
                time.sleep(0.01)
            return super()._next_fencing_token(run_dir)

    store = SlowRuntimeStateStore(root=root)
    barrier.wait(timeout=5)
    try:
        lease = store.acquire_lease(run_id=run_id, owner_id=owner_id, ttl_ms=30_000)
    except Exception as exc:  # noqa: BLE001 - the contract asserts this is the typed adapter error.
        results.put(("error", owner_id, _error_code(exc), type(exc).__name__))
        return
    results.put(("ok", owner_id, lease.fencing_token, ""))


def _runtime_state_file_lock_holder(run_dir: Path, ready: Any, release: Any) -> None:
    from app.core.adapters.runtime_state_store_local import _platform_lock_file, _platform_unlock_file

    lock_path = run_dir / ".runtime_state.lock"
    with lock_path.open("a+b") as lock_file:
        _platform_lock_file(lock_file)
        ready.put("locked")
        # Spawn-context suites can spend several seconds importing the backend
        # before the contender reaches acquire_lease; the holder must not time
        # out and release the lock before the assertion window starts.
        release.wait(timeout=60)
        _platform_unlock_file(lock_file)


def _runtime_state_ready_acquire_worker(
    root: Path,
    run_id: str,
    owner_id: str,
    ready: Any,
    start_acquire: Any,
    results: Any,
) -> None:
    from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore

    store = LocalRuntimeStateStore(root=root)
    ready.put("ready")
    start_acquire.wait(timeout=5)
    try:
        lease = store.acquire_lease(run_id=run_id, owner_id=owner_id, ttl_ms=30_000)
    except Exception as exc:  # noqa: BLE001 - the contract asserts this is the typed adapter error.
        results.put(("error", owner_id, _error_code(exc), type(exc).__name__))
        return
    results.put(("ok", owner_id, lease.fencing_token, ""))


def _release_payload(release_version: str = "v1") -> dict[str, Any]:
    return {
        "release_version": release_version,
        "idempotency_key": "idem-1",
        "artifact_ref": {
            "artifact_id": "artifact-1",
            "content_hash": f"sha256:{'a' * 64}",
            "manifest_ref": "manifests/artifact-1.json",
            "store": "product",
        },
    }


def _assert_release_manifest_has_no_source_leaks(manifest: dict[str, Any]) -> None:
    serialized = json.dumps(manifest, sort_keys=True)

    assert "skill_dir" not in serialized
    assert "source_path" not in serialized
    assert "package_bytes" not in serialized
    assert "/tmp/skills" not in serialized
    assert "/tmp/source" not in serialized
