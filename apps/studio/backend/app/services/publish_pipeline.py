from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class PublishArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_ref: dict[str, Any]
    release_version: str
    idempotency_key: str
    atomic_stage: str


class PublishReleaseConflict(Exception):
    pass


class PublishPartialFailure(Exception):
    pass


class ProductArtifactPublisher:
    def __init__(self, store: Any):
        self.store = store

    def publish_release(
        self,
        skill_id: str,
        release_version: str,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
    ) -> None:
        if self.store.has_release(skill_id, release_version):
            raise PublishReleaseConflict(f"Release {release_version} already exists for skill {skill_id}")

        payload = {
            "artifact_ref": artifact_ref,
            "idempotency_key": idempotency_key,
        }
        self.store.stage_release(skill_id, release_version, payload)

        try:
            self.store.commit_release(skill_id, release_version)
        except Exception as exc:
            try:
                self.store.rollback_release(skill_id, release_version)
            except Exception as rollback_exc:
                logger.warning(
                    "rollback_release failed after publish commit failure for skill_id=%s release_version=%s",
                    skill_id,
                    release_version,
                    exc_info=rollback_exc,
                )
            raise PublishPartialFailure(f"Commit release failed: {exc}") from exc
