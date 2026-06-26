"""Community Probe Catalog — Phase 2a verified read path (R4).

Downloads a signed manifest + content-addressed shards, verifies the Ed25519
signature and every shard digest, refuses an incompatible manifest protocol
version, and writes the mapped records into a **disposable cache** that is
isolated from the local evidence store. Every check fails closed: nothing is
written unless the whole chain verifies.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict

from app.core.adapters.gateway import EvidenceRecord
from app.services.community_catalog import parse_catalog_evidence


class VerifiedSyncError(RuntimeError):
    """Base error for the verified catalog read path."""


class ProtocolVersionRefused(VerifiedSyncError):
    """The manifest protocol_major is incompatible with this client."""


class SignatureVerificationFailed(VerifiedSyncError):
    """The manifest signature did not verify against the configured public key."""


class ShardDigestMismatch(VerifiedSyncError):
    """A downloaded shard did not match its manifest digest."""


class ShardRef(BaseModel):
    """One content-addressed shard listed in the manifest."""

    model_config = ConfigDict(extra="ignore")

    path: str
    sha256: str
    record_count: int = 0


class CatalogManifest(BaseModel):
    """Top-level catalog manifest (the signed document)."""

    model_config = ConfigDict(extra="ignore")

    protocol_major: int
    generated_at: str | None = None
    shards: list[ShardRef] = []


class CommunityCatalogCache(BaseModel):
    """Disposable, advisory cache of verified community evidence."""

    model_config = ConfigDict(extra="forbid")

    manifest_etag: str | None = None
    generated_at: str | None = None
    protocol_major: int = 0
    records: list[EvidenceRecord] = []


@dataclass(frozen=True)
class FetchResult:
    """One fetched resource: raw bytes plus its ETag."""

    content: bytes
    etag: str | None = None
    status_code: int = 200


@dataclass(frozen=True)
class SyncOutcome:
    """Result of a verified sync attempt."""

    status: str
    record_count: int
    manifest_etag: str | None
    protocol_major: int


Fetcher = Callable[[str], Awaitable[FetchResult]]


def verify_shard_digest(content: bytes, expected_sha256: str) -> bool:
    """Return whether the content's SHA-256 matches the expected digest."""
    return hashlib.sha256(content).hexdigest() == expected_sha256.strip().lower()


def verify_manifest_signature(
    *,
    manifest_bytes: bytes,
    signature_hex: str,
    public_key_hex: str,
) -> bool:
    """Verify a detached Ed25519 signature over the manifest bytes.

    Fails closed: malformed key/signature or a bad signature returns ``False``
    rather than raising.
    """
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(signature_hex), manifest_bytes)
        return True
    except Exception:
        return False


def manifest_protocol_compatible(manifest: CatalogManifest, client_major: int) -> bool:
    """Return whether the manifest protocol major matches this client."""
    return manifest.protocol_major == client_major


def _resolve_shard_url(shard_base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{shard_base_url.rstrip('/')}/{path.lstrip('/')}"


def make_httpx_fetcher(
    *,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Fetcher:
    """Return a :data:`Fetcher` backed by httpx (read-only GETs)."""

    async def fetch(url: str) -> FetchResult:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return FetchResult(
                content=response.content,
                etag=response.headers.get("etag"),
                status_code=response.status_code,
            )

    return fetch


class DisposableCatalogCacheStore:
    """A disposable on-disk cache, separate from the durable evidence store."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> CommunityCatalogCache:
        if not self._path.exists():
            return CommunityCatalogCache()
        return CommunityCatalogCache.model_validate_json(self._path.read_text(encoding="utf-8"))

    def save(self, cache: CommunityCatalogCache) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = cache.model_dump_json(indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()


async def sync_verified_catalog(
    *,
    manifest_url: str,
    signature_url: str,
    shard_base_url: str,
    public_key_hex: str,
    client_protocol_major: int,
    cache_store: DisposableCatalogCacheStore,
    fetch: Fetcher,
    prev_etag: str | None = None,
) -> SyncOutcome:
    """Fetch, verify, and cache the community catalog. Fails closed on any
    signature/digest/protocol failure without mutating the cache."""
    manifest_res = await fetch(manifest_url)
    if prev_etag is not None and manifest_res.etag is not None and manifest_res.etag == prev_etag:
        return SyncOutcome(
            status="unchanged",
            record_count=0,
            manifest_etag=manifest_res.etag,
            protocol_major=client_protocol_major,
        )

    signature_res = await fetch(signature_url)
    signature_hex = signature_res.content.decode("utf-8").strip()
    if not verify_manifest_signature(
        manifest_bytes=manifest_res.content,
        signature_hex=signature_hex,
        public_key_hex=public_key_hex,
    ):
        raise SignatureVerificationFailed("manifest signature verification failed")

    manifest = CatalogManifest.model_validate_json(manifest_res.content)
    if not manifest_protocol_compatible(manifest, client_protocol_major):
        raise ProtocolVersionRefused(
            f"manifest protocol_major={manifest.protocol_major} incompatible with client={client_protocol_major}"
        )

    records: list[EvidenceRecord] = []
    for shard in manifest.shards:
        shard_res = await fetch(_resolve_shard_url(shard_base_url, shard.path))
        if not verify_shard_digest(shard_res.content, shard.sha256):
            raise ShardDigestMismatch(f"shard digest mismatch: {shard.path}")
        payload = json.loads(shard_res.content)
        for wire_record in payload.get("records", []):
            records.append(parse_catalog_evidence(wire_record))

    cache_store.save(
        CommunityCatalogCache(
            manifest_etag=manifest_res.etag,
            generated_at=manifest.generated_at,
            protocol_major=manifest.protocol_major,
            records=records,
        )
    )
    return SyncOutcome(
        status="updated",
        record_count=len(records),
        manifest_etag=manifest_res.etag,
        protocol_major=manifest.protocol_major,
    )


__all__ = [
    "CatalogManifest",
    "CommunityCatalogCache",
    "DisposableCatalogCacheStore",
    "FetchResult",
    "ProtocolVersionRefused",
    "ShardDigestMismatch",
    "ShardRef",
    "SignatureVerificationFailed",
    "SyncOutcome",
    "VerifiedSyncError",
    "make_httpx_fetcher",
    "manifest_protocol_compatible",
    "sync_verified_catalog",
    "verify_manifest_signature",
    "verify_shard_digest",
]
