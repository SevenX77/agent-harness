"""HTTP client for Artifact Registry uploads."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.models.settings import AppSettings

logger = logging.getLogger(__name__)

PUBLISH_EXCLUDE_DIRS = frozenset({".workspace", ".git", ".kiro", "__pycache__"})
PUBLISH_EXCLUDE_FILES = frozenset({".DS_Store", "Thumbs.db"})
PUBLISH_EXCLUDE_SUFFIXES = frozenset({".pyc"})


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

        payload = response.json()
        if not isinstance(payload, dict):
            raise ArtifactRegistryApiError(status_code=response.status_code, body=response.text)

        logger.info(
            "artifact registry upload ok skill=%s status=%d", skill_id, response.status_code
        )
        return payload


def build_publish_package(skill_dir: Path) -> bytes:
    """Zip a skill directory into bytes for Artifact Registry upload."""
    if not skill_dir.exists() or not skill_dir.is_dir():
        raise ValueError(f"Publish skill_dir must be an existing directory: {skill_dir}")

    logger.info("build publish package skill_dir=%s", skill_dir)
    file_count = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill_dir.rglob("*")):
            rel_path = path.relative_to(skill_dir)
            excluded, reason = _should_exclude(rel_path)
            if excluded:
                logger.debug("excluding from publish package path=%s reason=%s", rel_path, reason)
                continue

            if path.is_symlink():
                target = path.readlink()
                logger.warning(
                    "symlink skipped in publish package path=%s target=%s", rel_path, target
                )
                continue
            if not path.is_file():
                continue

            try:
                archive.write(path, rel_path.as_posix())
                file_count += 1
            except OSError:
                logger.exception("failed reading publish package path=%s", rel_path)
                raise

    result = buffer.getvalue()
    logger.info(
        "publish package built skill_dir=%s files=%d bytes=%d", skill_dir, file_count, len(result)
    )
    return result


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


def _should_exclude(rel_path: Path) -> tuple[bool, str]:
    for part in rel_path.parts:
        if part in PUBLISH_EXCLUDE_DIRS:
            return True, f"excluded-dir:{part}"
    if rel_path.name in PUBLISH_EXCLUDE_FILES:
        return True, f"excluded-file:{rel_path.name}"
    if rel_path.suffix in PUBLISH_EXCLUDE_SUFFIXES:
        return True, f"excluded-suffix:{rel_path.suffix}"
    return False, ""
