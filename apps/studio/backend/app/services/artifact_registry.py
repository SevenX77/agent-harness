"""HTTP client for Artifact Registry uploads."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

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

        payload = response.json()
        if not isinstance(payload, dict):
            raise ArtifactRegistryApiError(status_code=response.status_code, body=response.text)

        logger.info("artifact registry upload ok skill=%s status=%d", skill_id, response.status_code)
        return payload
