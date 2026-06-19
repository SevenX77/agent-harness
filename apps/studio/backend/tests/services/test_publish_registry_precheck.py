"""N6: registry precheck rejects version/identity conflicts before any write.

The sidecar does a pre-publish check against the local product store ("成品库"):
if the requested ``release_version`` already exists with a *different* artifact
identity it must be rejected up-front (``PublishReleaseConflict``), before the
publisher stages or writes anything. A precheck against an identical existing
release (same artifact identity + idempotency key) is a benign pass.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.services.publish_pipeline import (
    ProductArtifactPublisher,
    PublishReleaseConflict,
)


class _MemoryReleaseStore:
    def __init__(self) -> None:
        self._releases: dict[tuple[str, str], dict[str, Any]] = {}
        self.stage_calls = 0
        self.commit_calls = 0

    def seed_release(self, skill_id: str, release_version: str, manifest: dict[str, Any]) -> None:
        self._releases[(skill_id, release_version)] = manifest

    def get_release(self, skill_id: str, release_version: str) -> dict[str, Any] | None:
        return self._releases.get((skill_id, release_version))

    def has_release(self, skill_id: str, release_version: str) -> bool:
        return (skill_id, release_version) in self._releases

    def stage_release(self, skill_id: str, release_version: str, payload: dict[str, Any]) -> None:
        self.stage_calls += 1
        self._releases[(skill_id, release_version)] = payload

    def commit_release(self, skill_id: str, release_version: str) -> None:
        self.commit_calls += 1


def _manifest(artifact_id: str, marker: str, idempotency_key: str) -> dict[str, Any]:
    content_hash = f"sha256:{marker * 64}"
    return {
        "release_version": "1.0.0",
        "artifact_ref": {
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "manifest_ref": f"manifests/{artifact_id}.json",
            "store": "product",
        },
        "idempotency_key": idempotency_key,
    }


def test_publisher_exposes_precheck_release() -> None:
    publisher = ProductArtifactPublisher(store=_MemoryReleaseStore())
    assert callable(getattr(publisher, "precheck_release", None))


def test_precheck_rejects_same_version_with_different_artifact_identity() -> None:
    store = _MemoryReleaseStore()
    existing = _manifest("skill-a", "a", "key-existing")
    store.seed_release("skill-a", "1.0.0", existing)
    publisher = ProductArtifactPublisher(store=store)

    new_ref = {
        "artifact_id": "skill-a",
        "content_hash": f"sha256:{'b' * 64}",
        "manifest_ref": "manifests/skill-a.json",
        "store": "product",
    }

    with pytest.raises(PublishReleaseConflict):
        publisher.precheck_release(
            skill_id="skill-a",
            release_version="1.0.0",
            artifact_ref=new_ref,
            idempotency_key="key-new",
        )

    # Precheck must not write anything.
    assert store.stage_calls == 0
    assert store.commit_calls == 0


def test_precheck_passes_for_identical_existing_release() -> None:
    store = _MemoryReleaseStore()
    existing = _manifest("skill-a", "a", "key-1")
    store.seed_release("skill-a", "1.0.0", existing)
    publisher = ProductArtifactPublisher(store=store)

    # Same artifact identity + same idempotency key → idempotent, not a conflict.
    publisher.precheck_release(
        skill_id="skill-a",
        release_version="1.0.0",
        artifact_ref=dict(existing["artifact_ref"]),
        idempotency_key="key-1",
    )


def test_precheck_passes_when_no_existing_release() -> None:
    store = _MemoryReleaseStore()
    publisher = ProductArtifactPublisher(store=store)

    publisher.precheck_release(
        skill_id="skill-a",
        release_version="1.0.0",
        artifact_ref={
            "artifact_id": "skill-a",
            "content_hash": f"sha256:{'a' * 64}",
            "manifest_ref": "manifests/skill-a.json",
            "store": "product",
        },
        idempotency_key="key-1",
    )
