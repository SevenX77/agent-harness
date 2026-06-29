"""Community Probe Catalog — Phase 2a upload client (R1/R3), Phase 6 (no queue).

The client posts sanitized :class:`EvidenceUpload` batches to the community gate
through a **clean open API**: the request carries only sanitized records — no
token, no credentials, no repo write key. All auth/abuse control lives
server-side (the gate rate-limits per client). Each batch carries an
``Idempotency-Key`` derived from its content so the gate can dedupe.

Phase 6: there is NO local offline/retry queue. A failed upload raises
:class:`CommunityUploadError` and parks nothing on disk; upload candidates are
re-derived from credentials evidence on the next probe / contribute and retried
with the SAME content-derived key, so the gate stays idempotent without any
local pending state.
"""

from __future__ import annotations

import hashlib
import json

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.community_catalog import EvidenceUpload

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


def batch_idempotency_key(uploads: list[EvidenceUpload]) -> str:
    """Return a content-derived idempotency key, stable for the same evidence set.

    The key is the SHA-256 of the canonicalized **sanitized upload payload** — every
    upload-meaningful field of each :class:`EvidenceUpload` (provider / model /
    endpoint / method / request_mapper / capability / model_type / modalities /
    probe_status / ...), NOT a hand-picked tuple. So if any semantic field changes the
    key changes and the gate will not wrongly dedupe; while two batches carrying the
    same evidence always collapse to the same key.

    The key is derived purely from the sanitized payload — never from a credential
    secret, API key, or local filesystem path. So re-deriving the SAME candidates from
    credentials on the next probe / contribute produces the SAME key (the gate dedupes
    it), which is exactly what lets Phase 6 drop the local retry queue.

    Determinism: each record is canonicalized with ``sort_keys`` and the batch is
    sorted by that canonical form, so element order never changes the key. The volatile
    ``observed_at`` timestamp is excluded so re-observing the same evidence stays
    idempotent — no timestamps, receipts, or random fields enter the key.
    """
    canonical_records = sorted(
        json.dumps(
            upload.model_dump(mode="json", exclude={"observed_at"}),
            sort_keys=True,
            ensure_ascii=False,
        )
        for upload in uploads
    )
    digest_input = json.dumps(canonical_records, ensure_ascii=False)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


class CommunityUploadError(RuntimeError):
    """Raised when a community upload fails (network / 5xx).

    There is no local queue: the caller reports the failure and the next probe or
    contribute re-derives the candidates from credentials and retries.
    """


class UploadAck(BaseModel):
    """Gate acknowledgement for one uploaded batch."""

    model_config = ConfigDict(extra="ignore")

    accepted: int = 0
    rejected: int = 0
    receipt_token: str | None = None
    detail: str | None = None


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
    ) -> UploadAck:
        """Upload one batch.

        On any failure raise :class:`CommunityUploadError` — nothing is parked
        locally; the batch is re-derived from credentials and retried on the next
        probe / contribute (the content-derived ``idempotency_key`` keeps it
        idempotent at the gate).
        """
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
            raise CommunityUploadError(
                f"community evidence upload failed (idempotency-key={idempotency_key}); "
                "candidates will be re-derived from credentials and retried"
            ) from exc
        return UploadAck.model_validate(data)


__all__ = [
    "EVIDENCE_BATCH_PATH",
    "PROTOCOL_MAJOR",
    "CommunityUploadClient",
    "CommunityUploadError",
    "UploadAck",
    "batch_idempotency_key",
    "community_upload_configured",
]
