from __future__ import annotations

import importlib
import logging

import pytest


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


class _MemoryReleaseStore:
    def __init__(self, *, fail_commit: bool = False, fail_rollback: bool = False) -> None:
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback
        self.visible_releases: dict[tuple[str, str], dict[str, object]] = {}
        self.staged_releases: dict[tuple[str, str], dict[str, object]] = {}

    def has_release(self, skill_id: str, release_version: str) -> bool:
        return (skill_id, release_version) in self.visible_releases

    def stage_release(self, skill_id: str, release_version: str, payload: dict[str, object]) -> None:
        self.staged_releases[(skill_id, release_version)] = payload

    def commit_release(self, skill_id: str, release_version: str) -> None:
        if self.fail_commit:
            raise OSError("simulated product store failure after staging")
        key = (skill_id, release_version)
        self.visible_releases[key] = self.staged_releases[key]

    def rollback_release(self, skill_id: str, release_version: str) -> None:
        if self.fail_rollback:
            raise OSError("simulated rollback failure")
        self.staged_releases.pop((skill_id, release_version), None)
