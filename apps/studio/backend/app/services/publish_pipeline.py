from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.artifact_registry import ArtifactRegistryApiError

logger = logging.getLogger(__name__)
_release_locks_guard = threading.Lock()
_release_locks: dict[tuple[str, str, str], threading.Lock] = {}


class PublishArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_ref: dict[str, Any]
    release_version: str
    idempotency_key: str
    atomic_stage: str


class PublishReleaseConflict(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class PublishPartialFailure(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ProductArtifactPublisher:
    def __init__(self, store: Any):
        self.store = store

    def _release_lock(self, skill_id: str, release_version: str) -> threading.Lock:
        store_root = getattr(self.store, "root", None)
        store_identity = str(store_root) if store_root is not None else str(id(self.store))
        key = (store_identity, skill_id, release_version)
        with _release_locks_guard:
            lock = _release_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                _release_locks[key] = lock
            return lock

    def publish_release(
        self,
        skill_id: str,
        release_version: str,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
        remote_sync: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        with self._release_lock(skill_id, release_version):
            existing = self._get_release(skill_id, release_version)
            if existing is not None:
                if existing.get("idempotency_key") == idempotency_key and self._artifact_identity(
                    existing.get("artifact_ref")
                ) == self._artifact_identity(artifact_ref):
                    return self._manifest_with_remote_sync(
                        existing,
                        remote_sync,
                        skill_id=skill_id,
                        release_version=release_version,
                        rollback_on_hard_failure=False,
                    )
                raise self._release_conflict(
                    skill_id,
                    release_version,
                    existing=existing,
                    artifact_ref=artifact_ref,
                    idempotency_key=idempotency_key,
                )

            payload = {
                "release_version": release_version,
                "artifact_ref": artifact_ref,
                "idempotency_key": idempotency_key,
                "created_at": datetime.now(UTC).isoformat(),
            }
            try:
                self.store.stage_release(skill_id, release_version, payload)
            except Exception as exc:
                release_manifest = self._release_from_matching_stage_conflict(
                    exc,
                    skill_id=skill_id,
                    release_version=release_version,
                    artifact_ref=artifact_ref,
                    idempotency_key=idempotency_key,
                )
                if release_manifest is not None:
                    return self._manifest_with_remote_sync(
                        release_manifest,
                        remote_sync,
                        skill_id=skill_id,
                        release_version=release_version,
                        rollback_on_hard_failure=False,
                    )
                self._raise_conflict_from_store_error(
                    exc,
                    skill_id=skill_id,
                    release_version=release_version,
                    artifact_ref=artifact_ref,
                    idempotency_key=idempotency_key,
                )
                raise

            try:
                self.store.commit_release(skill_id, release_version)
            except Exception as exc:
                self._raise_conflict_from_store_error(
                    exc,
                    skill_id=skill_id,
                    release_version=release_version,
                    artifact_ref=artifact_ref,
                    idempotency_key=idempotency_key,
                )
                compensation_details = self._rollback_release(skill_id, release_version)
                details = compensation_details or {
                    "phase": "commit_release",
                    "skill_id": skill_id,
                    "release_version": release_version,
                }
                raise PublishPartialFailure(f"Commit release failed: {exc}", details) from exc

            release_manifest = self._get_release(skill_id, release_version) or payload
            return self._manifest_with_remote_sync(
                release_manifest,
                remote_sync,
                skill_id=skill_id,
                release_version=release_version,
                rollback_on_hard_failure=True,
            )

    def _release_from_matching_stage_conflict(
        self,
        exc: Exception,
        *,
        skill_id: str,
        release_version: str,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if getattr(exc, "error_code", None) != "release.conflict":
            return None
        error_payload = getattr(exc, "error_payload", None)
        if not isinstance(error_payload, dict):
            return None
        staged_identity = error_payload.get("existing")
        if not isinstance(staged_identity, dict) or not staged_identity:
            return None
        if staged_identity.get("idempotency_key") != idempotency_key:
            return None
        if self._artifact_identity(staged_identity) != self._artifact_identity(artifact_ref):
            return None
        return self._wait_for_matching_release(
            skill_id,
            release_version,
            artifact_ref=artifact_ref,
            idempotency_key=idempotency_key,
        )

    def _wait_for_matching_release(
        self,
        skill_id: str,
        release_version: str,
        *,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            existing = self._get_release(skill_id, release_version)
            if existing is not None:
                if existing.get("idempotency_key") == idempotency_key and self._artifact_identity(
                    existing.get("artifact_ref")
                ) == self._artifact_identity(artifact_ref):
                    return existing
                return None
            time.sleep(0.025)
        return None

    def _get_release(self, skill_id: str, release_version: str) -> dict[str, Any] | None:
        get_release = getattr(self.store, "get_release", None)
        if callable(get_release):
            return get_release(skill_id, release_version)
        if self.store.has_release(skill_id, release_version):
            return {}
        return None

    def _raise_conflict_from_store_error(
        self,
        exc: Exception,
        *,
        skill_id: str,
        release_version: str,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
    ) -> None:
        if getattr(exc, "error_code", None) != "release.conflict":
            return
        error_payload = getattr(exc, "error_payload", None)
        existing = self._get_release(skill_id, release_version)
        details = self._release_conflict_details(
            skill_id,
            release_version,
            existing=existing,
            artifact_ref=artifact_ref,
            idempotency_key=idempotency_key,
        )
        if isinstance(error_payload, dict):
            existing_payload = error_payload.get("existing")
            if isinstance(existing_payload, dict) and existing_payload:
                details["existing"] = existing_payload
        raise PublishReleaseConflict(
            f"Release {release_version} already exists for skill {skill_id}",
            details,
        ) from exc

    def _release_conflict(
        self,
        skill_id: str,
        release_version: str,
        *,
        existing: dict[str, Any] | None,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
    ) -> PublishReleaseConflict:
        return PublishReleaseConflict(
            f"Release {release_version} already exists for skill {skill_id}",
            self._release_conflict_details(
                skill_id,
                release_version,
                existing=existing,
                artifact_ref=artifact_ref,
                idempotency_key=idempotency_key,
            ),
        )

    def _release_conflict_details(
        self,
        skill_id: str,
        release_version: str,
        *,
        existing: dict[str, Any] | None,
        artifact_ref: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        request_identity = self._artifact_identity(artifact_ref)
        request_identity.update(
            {
                "release_version": release_version,
                "idempotency_key": idempotency_key,
            }
        )
        existing_identity = self._artifact_identity(
            existing.get("artifact_ref") if isinstance(existing, dict) else None
        )
        if isinstance(existing, dict):
            existing_identity["release_version"] = str(existing.get("release_version") or release_version)
            existing_idempotency_key = existing.get("idempotency_key")
            if isinstance(existing_idempotency_key, str) and existing_idempotency_key:
                existing_identity["idempotency_key"] = existing_idempotency_key
        return {
            "skill_id": skill_id,
            "release_version": release_version,
            "existing": existing_identity,
            "request": request_identity,
        }

    def _artifact_identity(self, artifact_ref: Any) -> dict[str, Any]:
        if not isinstance(artifact_ref, dict):
            return {}
        identity: dict[str, Any] = {}
        for key in ("artifact_id", "content_hash", "manifest_ref"):
            value = artifact_ref.get(key)
            if isinstance(value, str) and value:
                identity[key] = value
        return identity

    def _rollback_release(self, skill_id: str, release_version: str) -> dict[str, Any] | None:
        try:
            self.store.rollback_release(skill_id, release_version)
        except Exception as rollback_exc:
            logger.warning(
                "rollback_release failed after publish commit failure for skill_id=%s release_version=%s",
                skill_id,
                release_version,
                exc_info=rollback_exc,
            )
            error_payload = getattr(rollback_exc, "error_payload", None)
            details = dict(error_payload) if isinstance(error_payload, dict) else {}
            details.update(
                {
                    "error_code": getattr(
                        rollback_exc,
                        "error_code",
                        "release.compensation_gc_failed",
                    ),
                    "phase": details.get("phase", "compensation_gc"),
                    "skill_id": details.get("skill_id", skill_id),
                    "release_version": details.get("release_version", release_version),
                    "error": details.get("error", str(rollback_exc)),
                }
            )
            return details
        return None

    def _manifest_with_remote_sync(
        self,
        release_manifest: dict[str, Any],
        remote_sync: Callable[[dict[str, Any]], Any] | None,
        *,
        skill_id: str,
        release_version: str,
        rollback_on_hard_failure: bool,
    ) -> dict[str, Any]:
        durable_manifest = deepcopy(release_manifest)
        durable_manifest.pop("remote_sync", None)
        response_manifest = deepcopy(durable_manifest)
        existing_state = self._get_remote_sync_state(skill_id, release_version)
        if isinstance(existing_state, dict) and existing_state.get("status") == "succeeded":
            response_manifest["remote_sync"] = existing_state
            return response_manifest
        if remote_sync is None:
            if existing_state is not None:
                response_manifest["remote_sync"] = existing_state
            return response_manifest

        try:
            remote_sync(deepcopy(durable_manifest))
        except Exception as exc:
            if not self._is_remote_sync_soft_failure(exc):
                compensation_details = None
                if rollback_on_hard_failure:
                    compensation_details = self._rollback_release(skill_id, release_version)
                if compensation_details is not None:
                    raise PublishPartialFailure(
                        f"Rollback release failed after remote sync failure: {exc}",
                        compensation_details,
                    ) from exc
                raise
            response_manifest["remote_sync"] = self._remote_sync_failure(exc)
            self._record_remote_sync_state(
                skill_id,
                release_version,
                response_manifest["remote_sync"],
            )
            logger.warning(
                "remote_sync failed after local release commit for skill_id=%s release_version=%s",
                skill_id,
                release_version,
                exc_info=True,
            )
        else:
            response_manifest["remote_sync"] = {"status": "succeeded"}
            self._record_remote_sync_state(
                skill_id,
                release_version,
                response_manifest["remote_sync"],
            )
        return response_manifest

    def _record_remote_sync_state(
        self,
        skill_id: str,
        release_version: str,
        state: dict[str, Any],
    ) -> None:
        record = getattr(self.store, "record_remote_sync_state", None)
        if callable(record):
            record(skill_id, release_version, deepcopy(state))

    def _get_remote_sync_state(self, skill_id: str, release_version: str) -> dict[str, Any] | None:
        get_state = getattr(self.store, "get_remote_sync_state", None)
        if not callable(get_state):
            return None
        state = get_state(skill_id, release_version)
        return deepcopy(state) if isinstance(state, dict) else None

    def _is_remote_sync_soft_failure(self, exc: Exception) -> bool:
        return isinstance(exc, (ArtifactRegistryApiError, httpx.RequestError))

    def _remote_sync_failure(self, exc: Exception) -> dict[str, Any]:
        details: dict[str, Any] = {}
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            details["status_code"] = status_code
        body = getattr(exc, "body", None)
        if isinstance(body, str):
            details["body"] = body

        failure: dict[str, Any] = {
            "status": "failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if details:
            failure["details"] = details
        return failure
