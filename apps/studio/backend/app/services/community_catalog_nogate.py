"""Community Probe Catalog — Phase 2 no-gate upload client.

The SIMPLE write-path: instead of POSTing sanitized evidence to a Cloudflare
gate, the desktop pushes :class:`EvidenceUpload` batches straight into the public
catalog repo's ``incoming/`` staging area using the user's own GitHub token. A
scheduled GitHub Action re-screens every record server-side (defense in depth)
and publishes the survivors (see ``services/community-catalog-gate``).

This deliberately gives the desktop catalog-repo write power — which the gate
design avoided — and so fits a single trusted publisher (the user's own machine).
Multi-user contribution still needs the gate. The staging object name is
content-derived, so re-pushing an identical batch is a no-op.
"""

from __future__ import annotations

import base64
import json

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.community_catalog import EvidenceUpload

GITHUB_API_VERSION = "2022-11-28"
INCOMING_DIR = "incoming"
_TIMEOUT_SECONDS = 10.0


def nogate_upload_configured(*, github_token: str, catalog_repo: str, enabled: bool) -> bool:
    """Return whether no-gate upload is fully configured and enabled.

    Dormant by default: the explicit enable flag, a GitHub token, and a target
    repo must all be present before the desktop pushes anything.
    """
    return bool(enabled and github_token.strip() and catalog_repo.strip())


def incoming_object_path(idempotency_key: str) -> str:
    """Content-addressed staging path; identical batches collide (idempotent)."""
    return f"{INCOMING_DIR}/{idempotency_key}.json"


def build_incoming_object(uploads: list[EvidenceUpload]) -> bytes:
    """Serialize a batch into the exact bytes the Action's mergeRecords reads."""
    body = {"records": [record.model_dump(mode="json") for record in uploads]}
    return json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")


class PushResult(BaseModel):
    """Outcome of staging one batch into the catalog repo's incoming/ area."""

    model_config = ConfigDict(extra="forbid")

    path: str
    created: bool


class NoGateUploadClient:
    """Pushes sanitized evidence batches into the catalog repo's incoming/ area."""

    def __init__(
        self,
        *,
        github_token: str,
        owner: str,
        repo: str,
        branch: str = "main",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        if not github_token.strip():
            raise ValueError("no-gate upload requires a GitHub token")
        if not owner.strip():
            raise ValueError("no-gate upload requires a repo owner")
        if not repo.strip():
            raise ValueError("no-gate upload requires a repo name")
        self._token = github_token.strip()
        self._owner = owner.strip()
        self._repo = repo.strip()
        self._branch = branch.strip() or "main"
        self._transport = transport
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    def _contents_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self._owner}/{self._repo}/contents/{path}"

    async def push_batch(
        self,
        uploads: list[EvidenceUpload],
        *,
        idempotency_key: str,
    ) -> PushResult:
        """Stage one batch. No-op (created=False) when the same batch already exists."""
        path = incoming_object_path(idempotency_key)
        url = self._contents_url(path)
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            existing = await client.get(url, headers=self._headers(), params={"ref": self._branch})
            if existing.status_code == 200:
                return PushResult(path=path, created=False)
            if existing.status_code != 404:
                existing.raise_for_status()
            encoded = base64.b64encode(build_incoming_object(uploads)).decode("ascii")
            response = await client.put(
                url,
                headers=self._headers(),
                json={
                    "message": f"chore(catalog): stage incoming batch {idempotency_key}",
                    "content": encoded,
                    "branch": self._branch,
                },
            )
            response.raise_for_status()
        return PushResult(path=path, created=True)


__all__ = [
    "GITHUB_API_VERSION",
    "NoGateUploadClient",
    "PushResult",
    "build_incoming_object",
    "incoming_object_path",
    "nogate_upload_configured",
]
