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
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict

from app.core.adapters.gateway import ProviderImportDraft
from app.models.llm_config import LLMCredentialsFile
from app.services.community_catalog import EvidenceUpload
from app.services.community_catalog_upload import (
    batch_idempotency_key,
    collect_uploadable_uploads,
)

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


class AutosharePlan(BaseModel):
    """A decided auto-share batch: what to upload and under which idempotency key."""

    model_config = ConfigDict(extra="forbid")

    uploads: list[EvidenceUpload]
    idempotency_key: str


def plan_autoshare(
    library: ProviderImportDraft,
    credentials: LLMCredentialsFile,
    *,
    github_token: str,
    catalog_repo: str,
    enabled: bool,
) -> AutosharePlan | None:
    """Decide whether to auto-share after a probe, and what batch to push.

    Returns ``None`` when no-gate upload is dormant or there is no uploadable
    evidence. Pure (no IO) so the decision stays unit-testable; the caller
    performs the actual push with :class:`NoGateUploadClient`.
    """
    if not nogate_upload_configured(github_token=github_token, catalog_repo=catalog_repo, enabled=enabled):
        return None
    uploads = collect_uploadable_uploads(library, credentials)
    if not uploads:
        return None
    return AutosharePlan(uploads=uploads, idempotency_key=batch_idempotency_key(uploads))


async def autoshare_probe_evidence(
    library: ProviderImportDraft,
    credentials: LLMCredentialsFile,
    *,
    github_token: str,
    catalog_repo: str,
    catalog_owner: str,
    enabled: bool,
    branch: str = "main",
    client_factory: Callable[..., NoGateUploadClient] = NoGateUploadClient,
) -> PushResult | None:
    """Decide + push in one call — the desktop's post-probe auto-share entrypoint.

    Returns ``None`` when dormant, when there is no uploadable evidence, or when
    the repo owner is not configured (the target repo cannot be located). Raises
    on a real push failure; the caller wraps this best-effort so a probe never
    fails just because background sharing did.
    """
    plan = plan_autoshare(
        library, credentials, github_token=github_token, catalog_repo=catalog_repo, enabled=enabled
    )
    if plan is None:
        return None
    if not catalog_owner.strip():
        return None
    client = client_factory(
        github_token=github_token, owner=catalog_owner, repo=catalog_repo, branch=branch
    )
    return await client.push_batch(plan.uploads, idempotency_key=plan.idempotency_key)


__all__ = [
    "GITHUB_API_VERSION",
    "AutosharePlan",
    "NoGateUploadClient",
    "PushResult",
    "autoshare_probe_evidence",
    "build_incoming_object",
    "incoming_object_path",
    "nogate_upload_configured",
    "plan_autoshare",
]
