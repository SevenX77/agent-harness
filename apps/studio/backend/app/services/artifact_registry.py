"""HTTP client for Artifact Registry uploads."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.models.settings import AppSettings

logger = logging.getLogger(__name__)


class ArtifactRegistryApiError(RuntimeError):
    """Raised when Artifact Registry returns a non-success HTTP status."""

    def __init__(self, *, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Artifact Registry returned {status_code}: {body}")


class ArtifactRegistryClient:
    """Small synchronous client for Artifact Registry package uploads."""

    def __init__(
        self,
        host: str,
        token: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.token = token
        self._http = http_client or httpx.Client()

    def upload_artifact(
        self,
        *,
        skill_id: str,
        package: bytes,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """POST a zip artifact package to the registry and return its payload."""
        if not self.host:
            raise ValueError("Artifact Registry host is not configured")
        if not self.token:
            raise ValueError("Artifact Registry token is not configured")

        logger.info("artifact registry upload start skill=%s bytes=%d", skill_id, len(package))
        try:
            response = self._http.request(
                "POST",
                f"{self.host}/api/v1/artifacts",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"metadata": json.dumps({"skill_id": skill_id, **metadata})},
                files={"package": (f"{skill_id}.zip", package, "application/zip")},
            )
        except httpx.RequestError as exc:
            logger.error("artifact registry network error skill=%s err=%s", skill_id, exc)
            raise

        if response.status_code >= 400:
            logger.warning(
                "artifact registry upload failed skill=%s status=%d body=%s",
                skill_id,
                response.status_code,
                response.text[:200],
            )
            raise ArtifactRegistryApiError(status_code=response.status_code, body=response.text)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ArtifactRegistryApiError(
                status_code=response.status_code,
                body=response.text,
            ) from exc
        if not isinstance(payload, dict):
            raise ArtifactRegistryApiError(status_code=response.status_code, body=response.text)

        logger.info(
            "artifact registry upload ok skill=%s status=%d", skill_id, response.status_code
        )
        return payload

    def sync_release_manifest(
        self,
        *,
        skill_id: str,
        release_manifest: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Sync release manifest metadata without uploading local package bytes."""
        if not self.host:
            raise ValueError("Artifact Registry host is not configured")
        if not self.token:
            raise ValueError("Artifact Registry token is not configured")

        logger.info("artifact registry release sync start skill=%s", skill_id)
        payload = {
            "skill_id": skill_id,
            "metadata": metadata,
            "release_manifest": release_manifest,
        }
        try:
            response = self._http.request(
                "POST",
                f"{self.host}/api/v1/releases",
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload,
            )
        except httpx.RequestError as exc:
            logger.error("artifact registry release sync network error skill=%s err=%s", skill_id, exc)
            raise

        if response.status_code >= 400:
            logger.warning(
                "artifact registry release sync failed skill=%s status=%d body=%s",
                skill_id,
                response.status_code,
                response.text[:200],
            )
            raise ArtifactRegistryApiError(status_code=response.status_code, body=response.text)

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise ArtifactRegistryApiError(
                status_code=response.status_code,
                body=response.text,
            ) from exc
        if not isinstance(response_payload, dict):
            raise ArtifactRegistryApiError(status_code=response.status_code, body=response.text)

        logger.info(
            "artifact registry release sync ok skill=%s status=%d", skill_id, response.status_code
        )
        return response_payload


def build_publish_metadata(
    skill_id: str,
    app_settings: AppSettings,
    *,
    version: str = "1.0.0",
) -> dict[str, Any]:
    """Assemble Artifact Registry metadata for a publish request."""
    author = app_settings.user_id.strip()
    if not author:
        raise ValueError("Publish requires non-empty user_id in app_settings")

    return {
        "skill_id": skill_id,
        "author": author,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "version": version,
    }


def sync_product_artifact_release(
    *,
    skill_id: str,
    release_manifest: dict[str, Any],
    store: Any,
    registry: Any,
    app_settings: AppSettings,
    version: str,
) -> dict[str, Any]:
    """Sync a committed ProductArtifactStore release to the remote registry."""
    artifact_ref = release_manifest["artifact_ref"]
    if not isinstance(artifact_ref, dict):
        raise ValueError("release manifest artifact_ref must be an object")
    content_hash = artifact_ref["content_hash"]
    if not isinstance(content_hash, str):
        raise ValueError("release manifest content_hash must be a string")

    store.get(content_hash)
    metadata = build_publish_metadata(skill_id, app_settings, version=version)
    metadata["artifact_ref"] = artifact_ref
    metadata["package_kind"] = "product_artifact"
    metadata["release_version"] = release_manifest["release_version"]
    return registry.sync_release_manifest(
        skill_id=skill_id,
        release_manifest=release_manifest,
        metadata=metadata,
    )
