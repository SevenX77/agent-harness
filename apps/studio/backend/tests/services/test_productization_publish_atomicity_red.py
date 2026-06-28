from __future__ import annotations

import importlib
import logging
import threading

import httpx
import pytest
from app.core.adapters.http_transport import StudioAdapterError
from app.services.artifact_registry import ArtifactRegistryApiError


def test_publish_pipeline_exposes_atomic_release_publisher() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")

    assert callable(getattr(pipeline, "ProductArtifactPublisher", None))
    assert callable(getattr(pipeline, "PublishReleaseConflict", None))
    assert callable(getattr(pipeline, "PublishPartialFailure", None))


def test_publish_pipeline_rejects_duplicate_release_version_before_overwrite() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    conflict = getattr(pipeline, "PublishReleaseConflict", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if conflict is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher and PublishReleaseConflict must define duplicate-release behavior")

    publisher = publisher_cls(store=_MemoryReleaseStore())

    publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref={"artifact_id": "artifact-1", "content_hash": f"sha256:{'a' * 64}"},
        idempotency_key="idem-1",
    )

    with pytest.raises(conflict):
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref={"artifact_id": "artifact-2", "content_hash": f"sha256:{'b' * 64}"},
            idempotency_key="idem-2",
        )


def test_publish_pipeline_idempotency_retry_returns_existing_release_manifest() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must define idempotent retry behavior")

    publisher = publisher_cls(store=_MemoryReleaseStore())
    artifact_ref = {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
    }

    first = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=artifact_ref,
        idempotency_key="idem-1",
    )
    retry = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=artifact_ref,
        idempotency_key="idem-1",
    )

    assert retry == first
    assert retry["release_version"] == "2026.06.11"
    assert retry["artifact_ref"]["manifest_ref"] == "manifests/artifact-1.json"


def test_publish_pipeline_same_idempotency_key_with_different_artifact_conflicts() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    conflict = getattr(pipeline, "PublishReleaseConflict", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if conflict is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must reject idempotency key reuse for a different artifact")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)
    first_artifact_ref = {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
    }
    second_artifact_ref = {
        "artifact_id": "artifact-2",
        "content_hash": f"sha256:{'b' * 64}",
        "manifest_ref": "manifests/artifact-2.json",
    }

    first = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=first_artifact_ref,
        idempotency_key="idem-1",
    )

    with pytest.raises(conflict) as exc_info:
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref=second_artifact_ref,
            idempotency_key="idem-1",
        )

    assert store.stage_calls == 1
    assert store.commit_calls == 1
    assert store.get_release("text-segmentation", "2026.06.11") == first
    details = getattr(exc_info.value, "details", None)
    assert details["release_version"] == "2026.06.11"
    assert details["existing"]["artifact_id"] == "artifact-1"
    assert details["existing"]["content_hash"] == f"sha256:{'a' * 64}"
    assert details["request"]["artifact_id"] == "artifact-2"
    assert details["request"]["idempotency_key"] == "idem-1"


def test_publish_pipeline_same_idempotency_key_same_artifact_waits_out_stage_conflict() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must return idempotent release after matching stage conflict")

    shared = _SharedStageConflictState()
    first_publisher = publisher_cls(store=_StageConflictReleaseStore(shared))
    second_publisher = publisher_cls(store=_StageConflictReleaseStore(shared))
    artifact_ref = {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
    }
    results: dict[str, dict[str, object] | Exception] = {}

    def first_publish() -> None:
        try:
            results["first"] = first_publisher.publish_release(
                skill_id="text-segmentation",
                release_version="2026.06.11",
                artifact_ref=artifact_ref,
                idempotency_key="idem-1",
            )
        except Exception as exc:
            results["first"] = exc

    def second_publish() -> None:
        try:
            results["second"] = second_publisher.publish_release(
                skill_id="text-segmentation",
                release_version="2026.06.11",
                artifact_ref=artifact_ref,
                idempotency_key="idem-1",
            )
        except Exception as exc:
            results["second"] = exc

    first_thread = threading.Thread(target=first_publish)
    first_thread.start()
    assert shared.stage_started.wait(timeout=5)

    second_thread = threading.Thread(target=second_publish)
    second_thread.start()
    assert shared.stage_conflict_seen.wait(timeout=5)
    shared.allow_commit.set()

    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert not isinstance(results.get("first"), Exception)
    assert not isinstance(results.get("second"), Exception)
    assert results["second"] == results["first"]
    assert shared.visible_releases[("text-segmentation", "2026.06.11")] == results["first"]
    assert shared.staged_releases == {}


def test_publish_pipeline_conflict_details_include_existing_release_identity() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    conflict = getattr(pipeline, "PublishReleaseConflict", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if conflict is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must expose existing release identity on conflict")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)
    first_artifact_ref = {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
    }
    second_artifact_ref = {
        "artifact_id": "artifact-2",
        "content_hash": f"sha256:{'b' * 64}",
        "manifest_ref": "manifests/artifact-2.json",
    }
    publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=first_artifact_ref,
        idempotency_key="idem-1",
    )

    with pytest.raises(conflict) as exc_info:
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref=second_artifact_ref,
            idempotency_key="idem-2",
        )

    details = getattr(exc_info.value, "details", None)
    assert details["skill_id"] == "text-segmentation"
    assert details["release_version"] == "2026.06.11"
    assert details["existing"]["artifact_id"] == "artifact-1"
    assert details["existing"]["content_hash"] == f"sha256:{'a' * 64}"
    assert details["existing"]["release_version"] == "2026.06.11"
    assert details["request"]["artifact_id"] == "artifact-2"
    assert details["request"]["content_hash"] == f"sha256:{'b' * 64}"
    assert store.raw_release("text-segmentation", "2026.06.11")["artifact_ref"] == first_artifact_ref


def test_publish_pipeline_idempotency_retry_updates_durable_remote_sync_state() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must define idempotent retry behavior")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)
    calls: list[str] = []
    artifact_ref = {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
    }

    def fail_remote_sync(_release: dict[str, object]) -> None:
        calls.append("fail")
        raise ArtifactRegistryApiError(status_code=503, body="registry unavailable")

    first = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=artifact_ref,
        idempotency_key="idem-1",
        remote_sync=fail_remote_sync,
    )

    def succeed_remote_sync(_release: dict[str, object]) -> None:
        calls.append("succeed")

    retry = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=artifact_ref,
        idempotency_key="idem-1",
        remote_sync=succeed_remote_sync,
    )

    assert calls == ["fail", "succeed"]
    assert first["remote_sync"]["status"] == "failed"
    assert retry["remote_sync"] == {"status": "succeeded"}
    assert store.staged_releases == {}
    assert store.stage_calls == 1
    assert store.commit_calls == 1
    committed = store.get_release("text-segmentation", "2026.06.11")
    assert committed is not None
    assert committed["remote_sync"] == {"status": "succeeded"}
    assert store.raw_release("text-segmentation", "2026.06.11")["artifact_ref"] == artifact_ref
    assert "remote_sync" not in store.raw_release("text-segmentation", "2026.06.11")


def test_publish_pipeline_idempotency_retry_does_not_downgrade_succeeded_remote_sync() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must preserve terminal remote sync state")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)
    calls: list[str] = []
    artifact_ref = {
        "artifact_id": "artifact-1",
        "content_hash": f"sha256:{'a' * 64}",
        "manifest_ref": "manifests/artifact-1.json",
    }

    def succeed_remote_sync(_release: dict[str, object]) -> None:
        calls.append("succeed")

    first = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=artifact_ref,
        idempotency_key="idem-1",
        remote_sync=succeed_remote_sync,
    )

    def fail_if_called(_release: dict[str, object]) -> None:
        calls.append("retry")
        raise ArtifactRegistryApiError(status_code=503, body="registry unavailable")

    retry = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref=artifact_ref,
        idempotency_key="idem-1",
        remote_sync=fail_if_called,
    )

    assert calls == ["succeed"]
    assert first["remote_sync"] == {"status": "succeeded"}
    assert retry["remote_sync"] == {"status": "succeeded"}
    committed = store.get_release("text-segmentation", "2026.06.11")
    assert committed is not None
    assert committed["remote_sync"] == {"status": "succeeded"}


def test_publish_pipeline_commits_local_release_when_remote_sync_fails() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must define post-commit remote sync behavior")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)

    def fail_remote_sync(_release: dict[str, object]) -> None:
        request = httpx.Request("POST", "https://registry.example.test/api/v1/artifacts")
        raise httpx.ConnectError("registry unavailable", request=request)

    result = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref={
            "artifact_id": "artifact-1",
            "content_hash": f"sha256:{'a' * 64}",
            "manifest_ref": "manifests/artifact-1.json",
        },
        idempotency_key="idem-1",
        remote_sync=fail_remote_sync,
    )

    assert store.has_release("text-segmentation", "2026.06.11")
    committed = store.get_release("text-segmentation", "2026.06.11")
    assert committed is not None
    assert committed["release_version"] == "2026.06.11"
    assert committed["artifact_ref"]["artifact_id"] == "artifact-1"
    assert store.staged_releases == {}
    assert result["release_version"] == "2026.06.11"
    assert result["artifact_ref"]["manifest_ref"] == "manifests/artifact-1.json"
    assert result["remote_sync"]["status"] == "failed"
    assert result["remote_sync"]["error_type"] == "ConnectError"
    assert "registry unavailable" in result["remote_sync"]["error"]
    assert committed["remote_sync"]["status"] == "failed"
    assert committed["remote_sync"]["error_type"] == "ConnectError"


def test_publish_pipeline_remote_sync_failure_does_not_pollute_committed_manifest() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must define post-commit remote sync behavior")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)

    def mutate_then_fail(release: dict[str, object]) -> None:
        release["remote_sync"] = {"status": "callback_mutated"}
        artifact_ref = release["artifact_ref"]
        assert isinstance(artifact_ref, dict)
        artifact_ref["callback_mutated"] = True
        raise ArtifactRegistryApiError(status_code=503, body="registry unavailable")

    result = publisher.publish_release(
        skill_id="text-segmentation",
        release_version="2026.06.11",
        artifact_ref={
            "artifact_id": "artifact-1",
            "content_hash": f"sha256:{'a' * 64}",
            "manifest_ref": "manifests/artifact-1.json",
        },
        idempotency_key="idem-1",
        remote_sync=mutate_then_fail,
    )

    assert result["remote_sync"]["status"] == "failed"
    committed = store.get_release("text-segmentation", "2026.06.11")
    assert committed is not None
    assert committed["remote_sync"]["status"] == "failed"
    raw_committed = store.raw_release("text-segmentation", "2026.06.11")
    assert "remote_sync" not in raw_committed
    assert "callback_mutated" not in committed["artifact_ref"]
    assert "callback_mutated" not in raw_committed["artifact_ref"]


def test_publish_pipeline_rolls_back_when_remote_sync_raises_local_artifact_error() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must define local invariant failure behavior")

    store = _MemoryReleaseStore()
    publisher = publisher_cls(store=store)

    def fail_local_store(_release: dict[str, object]) -> None:
        raise StudioAdapterError("artifact.hash_mismatch", {"expected": "a", "actual": "b"})

    with pytest.raises(StudioAdapterError) as exc_info:
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref={
                "artifact_id": "artifact-1",
                "content_hash": f"sha256:{'a' * 64}",
                "manifest_ref": "manifests/artifact-1.json",
            },
            idempotency_key="idem-1",
            remote_sync=fail_local_store,
        )

    assert exc_info.value.error_code == "artifact.hash_mismatch"
    assert store.visible_releases == {}
    assert store.staged_releases == {}


def test_publish_pipeline_exposes_compensation_gc_when_remote_hard_failure_rollback_fails() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    partial_failure = getattr(pipeline, "PublishPartialFailure", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if partial_failure is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must expose compensation details after remote hard failure")

    store = _MemoryReleaseStore(fail_rollback=True)
    publisher = publisher_cls(store=store)

    def fail_local_store(_release: dict[str, object]) -> None:
        raise StudioAdapterError("artifact.hash_mismatch", {"expected": "a", "actual": "b"})

    with pytest.raises(partial_failure) as exc_info:
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref={
                "artifact_id": "artifact-1",
                "content_hash": f"sha256:{'a' * 64}",
                "manifest_ref": "manifests/artifact-1.json",
            },
            idempotency_key="idem-1",
            remote_sync=fail_local_store,
        )

    details = getattr(exc_info.value, "details", None)
    assert details["phase"] == "compensation_gc"
    assert details["error_code"] == "release.compensation_gc_failed"
    assert details["skill_id"] == "text-segmentation"
    assert details["release_version"] == "2026.06.11"


def test_publish_pipeline_rolls_back_visible_release_on_partial_failure() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    partial_failure = getattr(pipeline, "PublishPartialFailure", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if partial_failure is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher and PublishPartialFailure must define atomic rollback behavior")

    store = _MemoryReleaseStore(fail_commit=True)
    publisher = publisher_cls(store=store)

    with pytest.raises(partial_failure):
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref={"artifact_id": "artifact-1", "content_hash": f"sha256:{'a' * 64}"},
            idempotency_key="idem-1",
        )

    assert store.visible_releases == {}
    assert store.staged_releases == {}


def test_publish_pipeline_logs_rollback_failure(caplog: pytest.LogCaptureFixture) -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    partial_failure = getattr(pipeline, "PublishPartialFailure", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if partial_failure is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher and PublishPartialFailure must define rollback failure logging")

    store = _MemoryReleaseStore(fail_commit=True, fail_rollback=True)
    publisher = publisher_cls(store=store)
    caplog.set_level(logging.WARNING, logger="app.services.publish_pipeline")

    with pytest.raises(partial_failure):
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref={"artifact_id": "artifact-1", "content_hash": f"sha256:{'a' * 64}"},
            idempotency_key="idem-1",
        )

    assert "rollback_release failed after publish commit failure" in caplog.text
    assert "text-segmentation" in caplog.text
    assert "2026.06.11" in caplog.text


def test_publish_pipeline_exposes_compensation_gc_phase_when_rollback_fails() -> None:
    pipeline = importlib.import_module("app.services.publish_pipeline")
    partial_failure = getattr(pipeline, "PublishPartialFailure", None)
    publisher_cls = getattr(pipeline, "ProductArtifactPublisher", None)
    if partial_failure is None or publisher_cls is None:
        pytest.fail("ProductArtifactPublisher must expose compensation GC failure details")

    store = _MemoryReleaseStore(fail_commit=True, fail_rollback=True)
    publisher = publisher_cls(store=store)

    with pytest.raises(partial_failure) as exc_info:
        publisher.publish_release(
            skill_id="text-segmentation",
            release_version="2026.06.11",
            artifact_ref={"artifact_id": "artifact-1", "content_hash": f"sha256:{'a' * 64}"},
            idempotency_key="idem-1",
        )

    details = getattr(exc_info.value, "details", None)
    assert details["phase"] == "compensation_gc"
    assert details["error_code"] == "release.compensation_gc_failed"
    assert details["skill_id"] == "text-segmentation"
    assert details["release_version"] == "2026.06.11"
    assert store.visible_releases == {}
    assert store.get_release("text-segmentation", "2026.06.11") is None
    assert ("text-segmentation", "2026.06.11") in store.staged_releases


class _MemoryReleaseStore:
    def __init__(self, *, fail_commit: bool = False, fail_rollback: bool = False) -> None:
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback
        self.visible_releases: dict[tuple[str, str], dict[str, object]] = {}
        self.staged_releases: dict[tuple[str, str], dict[str, object]] = {}
        self.remote_sync_states: dict[tuple[str, str], dict[str, object]] = {}
        self.stage_calls = 0
        self.commit_calls = 0

    def has_release(self, skill_id: str, release_version: str) -> bool:
        return (skill_id, release_version) in self.visible_releases

    def get_release(self, skill_id: str, release_version: str) -> dict[str, object] | None:
        release = self.visible_releases.get((skill_id, release_version))
        if release is None:
            return None
        result = dict(release)
        remote_sync = self.get_remote_sync_state(skill_id, release_version)
        if remote_sync is not None:
            result["remote_sync"] = remote_sync
        return result

    def raw_release(self, skill_id: str, release_version: str) -> dict[str, object]:
        return self.visible_releases[(skill_id, release_version)]

    def stage_release(self, skill_id: str, release_version: str, payload: dict[str, object]) -> None:
        self.stage_calls += 1
        self.staged_releases[(skill_id, release_version)] = payload

    def commit_release(self, skill_id: str, release_version: str) -> None:
        self.commit_calls += 1
        if self.fail_commit:
            raise OSError("simulated product store failure after staging")
        key = (skill_id, release_version)
        self.visible_releases[key] = self.staged_releases.pop(key)

    def rollback_release(self, skill_id: str, release_version: str) -> None:
        if self.fail_rollback:
            raise OSError("simulated rollback failure")
        self.staged_releases.pop((skill_id, release_version), None)
        self.visible_releases.pop((skill_id, release_version), None)

    def record_remote_sync_state(
        self,
        skill_id: str,
        release_version: str,
        state: dict[str, object],
    ) -> None:
        self.remote_sync_states[(skill_id, release_version)] = dict(state)

    def get_remote_sync_state(self, skill_id: str, release_version: str) -> dict[str, object] | None:
        state = self.remote_sync_states.get((skill_id, release_version))
        return dict(state) if state is not None else None


class _SharedStageConflictState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.visible_releases: dict[tuple[str, str], dict[str, object]] = {}
        self.staged_releases: dict[tuple[str, str], dict[str, object]] = {}
        self.stage_started = threading.Event()
        self.stage_conflict_seen = threading.Event()
        self.allow_commit = threading.Event()


class _StageConflictReleaseStore:
    def __init__(self, shared: _SharedStageConflictState) -> None:
        self.shared = shared

    def has_release(self, skill_id: str, release_version: str) -> bool:
        return (skill_id, release_version) in self.shared.visible_releases

    def get_release(self, skill_id: str, release_version: str) -> dict[str, object] | None:
        release = self.shared.visible_releases.get((skill_id, release_version))
        return dict(release) if release is not None else None

    def stage_release(self, skill_id: str, release_version: str, payload: dict[str, object]) -> None:
        key = (skill_id, release_version)
        with self.shared.lock:
            existing = self.shared.visible_releases.get(key)
            if existing is not None:
                raise _release_conflict_error(skill_id, release_version, payload, existing=existing)
            staged = self.shared.staged_releases.get(key)
            if staged is not None:
                self.shared.stage_conflict_seen.set()
                raise _release_conflict_error(skill_id, release_version, payload, existing=staged)
            self.shared.staged_releases[key] = dict(payload)
            self.shared.stage_started.set()

    def commit_release(self, skill_id: str, release_version: str) -> None:
        assert self.shared.allow_commit.wait(timeout=5)
        key = (skill_id, release_version)
        with self.shared.lock:
            self.shared.visible_releases[key] = self.shared.staged_releases.pop(key)

    def rollback_release(self, skill_id: str, release_version: str) -> None:
        key = (skill_id, release_version)
        with self.shared.lock:
            self.shared.staged_releases.pop(key, None)
            self.shared.visible_releases.pop(key, None)


def _release_conflict_error(
    skill_id: str,
    release_version: str,
    request: dict[str, object],
    *,
    existing: dict[str, object],
) -> StudioAdapterError:
    return StudioAdapterError(
        "release.conflict",
        {
            "skill_id": skill_id,
            "release_version": release_version,
            "existing": _release_identity(existing),
            "request": _release_identity(request),
        },
    )


def _release_identity(manifest: dict[str, object]) -> dict[str, object]:
    artifact_ref = manifest.get("artifact_ref")
    if not isinstance(artifact_ref, dict):
        artifact_ref = manifest
    identity: dict[str, object] = {}
    for key in ("artifact_id", "content_hash", "manifest_ref"):
        value = artifact_ref.get(key)
        if isinstance(value, str) and value:
            identity[key] = value
    for key in ("release_version", "idempotency_key"):
        value = manifest.get(key)
        if isinstance(value, str) and value:
            identity[key] = value
    return identity
