"""Community Probe Catalog — Phase 2a upload client (R1/R3/R6).

The client posts sanitized :class:`EvidenceUpload` batches to the community gate
through a **clean open API**: the request carries only sanitized records — no
token, no credentials, no repo write key. All auth/abuse control lives
server-side (the gate rate-limits per client). Each batch carries an
``Idempotency-Key`` so the gate can dedupe, and failed batches are parked in a
local offline queue for later retry — the key is preserved so a retry stays
idempotent.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from app.core.adapters.gateway import ProviderImportDraft
from app.models.llm_config import LLMCredentialsFile
from app.services.community_catalog import (
    EvidenceUpload,
    build_upload_record,
    is_uploadable,
)

EVIDENCE_BATCH_PATH = "/v1/evidence/batches"
PROTOCOL_MAJOR = 1
_TIMEOUT_SECONDS = 10.0


def community_upload_configured(*, gate_url: str, enabled: bool) -> bool:
    """Return whether community upload is enabled and has a gate to post to.

    The client needs no token — the gate is a clean open API. Upload activates
    when the deployment flag is on and a gate URL is set; both ship with
    on-by-default values, so contribution works out of the box and is governed
    by the single user-facing catalog toggle.
    """
    return bool(enabled and gate_url.strip())


def collect_uploadable_uploads(
    library: ProviderImportDraft,
    credentials: LLMCredentialsFile,
) -> list[EvidenceUpload]:
    """Build sanitized upload payloads from probe-verified evidence.

    Each record's endpoint base URL is joined from active credentials so the
    allowlist/fingerprint decision happens per endpoint; non-uploadable evidence
    (e.g. provider-list-observed) is skipped.
    """
    uploads: list[EvidenceUpload] = []
    for record in library.evidence_records:
        if not is_uploadable(record):
            continue
        endpoint = (
            credentials.provider_endpoints.get(record.endpoint_id) if record.endpoint_id else None
        )
        base_url = endpoint.base_url if endpoint is not None else None
        uploads.append(build_upload_record(record, base_url=base_url))
    return uploads


def batch_idempotency_key(uploads: list[EvidenceUpload]) -> str:
    """Return a content-derived idempotency key, stable for the same evidence set."""
    digest_input = json.dumps(
        sorted(
            [
                u.provider_id or "",
                u.provider_model_id or "",
                u.endpoint_fingerprint or "",
                u.method_id or "",
            ]
            for u in uploads
        ),
        ensure_ascii=False,
    )
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


class CommunityUploadError(RuntimeError):
    """Base error for community upload failures."""


class UploadDeferred(CommunityUploadError):
    """Upload failed and the batch was parked in the offline queue for retry."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(f"upload deferred to offline queue: {idempotency_key}")
        self.idempotency_key = idempotency_key


class UploadAck(BaseModel):
    """Gate acknowledgement for one uploaded batch."""

    model_config = ConfigDict(extra="ignore")

    accepted: int = 0
    rejected: int = 0
    receipt_token: str | None = None
    detail: str | None = None


class QueuedBatch(BaseModel):
    """A batch parked for offline retry, with its original idempotency key."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    protocol_major: int
    records: list[EvidenceUpload]
    enqueued_at: str | None = None


class DrainResult(BaseModel):
    """Outcome of draining the offline queue."""

    model_config = ConfigDict(extra="forbid")

    succeeded: int = 0
    remaining: int = 0


class OfflineUploadQueue:
    """A simple JSON-file queue of batches awaiting retry."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[QueuedBatch]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8") or "[]")
        return [QueuedBatch.model_validate(item) for item in raw]

    def enqueue(self, batch: QueuedBatch) -> None:
        batches = self.load()
        batches.append(batch)
        self._write(batches)

    def replace(self, batches: list[QueuedBatch]) -> None:
        self._write(batches)

    def clear(self) -> None:
        self._write([])

    def _write(self, batches: list[QueuedBatch]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([b.model_dump(mode="json") for b in batches], ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class CommunityUploadClient:
    """Client that uploads sanitized evidence batches to the gate.

    Clean open API: no token is sent. The gate takes only sanitized records and
    rate-limits per client server-side.
    """

    def __init__(
        self,
        *,
        gate_url: str,
        protocol_major: int = PROTOCOL_MAJOR,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        if not gate_url.strip():
            raise ValueError("community upload requires a gate URL")
        self._gate_url = gate_url.rstrip("/")
        self._protocol_major = protocol_major
        self._transport = transport
        self._timeout = timeout

    async def upload_batch(
        self,
        records: list[EvidenceUpload],
        *,
        idempotency_key: str,
        queue: OfflineUploadQueue | None = None,
    ) -> UploadAck:
        """Upload one batch. On failure, park it in ``queue`` (if given) and
        raise :class:`UploadDeferred`."""
        payload = {
            "protocol_major": self._protocol_major,
            "records": [record.model_dump(mode="json") for record in records],
        }
        headers = {
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._gate_url}{EVIDENCE_BATCH_PATH}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            if queue is not None:
                queue.enqueue(
                    QueuedBatch(
                        idempotency_key=idempotency_key,
                        protocol_major=self._protocol_major,
                        records=list(records),
                        enqueued_at=_now_iso(),
                    )
                )
            raise UploadDeferred(idempotency_key) from exc
        return UploadAck.model_validate(data)

    async def drain_queue(self, queue: OfflineUploadQueue) -> DrainResult:
        """Retry every parked batch; keep the ones that still fail."""
        remaining: list[QueuedBatch] = []
        succeeded = 0
        for batch in queue.load():
            try:
                await self.upload_batch(batch.records, idempotency_key=batch.idempotency_key)
                succeeded += 1
            except CommunityUploadError:
                remaining.append(batch)
        queue.replace(remaining)
        return DrainResult(succeeded=succeeded, remaining=len(remaining))


__all__ = [
    "EVIDENCE_BATCH_PATH",
    "PROTOCOL_MAJOR",
    "CommunityUploadClient",
    "CommunityUploadError",
    "DrainResult",
    "OfflineUploadQueue",
    "QueuedBatch",
    "UploadAck",
    "UploadDeferred",
    "batch_idempotency_key",
    "collect_uploadable_uploads",
    "community_upload_configured",
]
