"""Import-draft storage and append-only provider evidence records."""

from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from app.core.adapters.gateway import (
    EVIDENCE_LIBRARY_DRAFT_ID,
    EvidenceRecord,
    ImportDraftStore,
    ProviderImportDraft,
    RouteCandidate,
    materialize_import_draft_candidates,
)
from app.models.llm_config import ProviderEndpoint, ProviderRoute
from app.services.llm_credentials import (
    credentials_path as default_credentials_path,
)
from app.services.llm_credentials import (
    load_credentials,
    save_credentials,
)
from app.services.llm_paths import import_drafts_path

ConflictMode = Literal["merge"]
_APPLY_LOCK = threading.Lock()


class DraftNotFound(KeyError):
    """Requested import draft does not exist."""


class DraftExpired(ValueError):
    """Import draft is expired and cannot be applied."""


class DraftApplyConflict(ValueError):
    """Import draft collides with active config and needs explicit choice."""


class RemoteCatalogSyncError(RuntimeError):
    """Raised when the remote evidence catalog cannot be fetched or parsed."""


def drafts_path() -> Path:
    """Return the import draft and evidence store path."""
    return import_drafts_path()


def create_draft(
    draft: ProviderImportDraft,
    *,
    path: Path | None = None,
) -> ProviderImportDraft:
    """Create or replace one draft in the transient store."""
    return _store(path).save_draft(draft)


def load_draft(draft_id: str, *, path: Path | None = None) -> ProviderImportDraft:
    """Load one draft or raise DraftNotFound."""
    try:
        return _store(path).load_draft(draft_id)
    except KeyError as exc:
        raise DraftNotFound(draft_id) from exc


def load_evidence_library(
    *,
    path: Path | None = None,
    draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
) -> ProviderImportDraft:
    """Load the durable evidence library, returning an empty one if absent."""
    return _store(path).load_evidence_library(draft_id=draft_id)


def save_draft(draft: ProviderImportDraft, *, path: Path | None = None) -> ProviderImportDraft:
    """Atomically save one draft."""
    return _store(path).save_draft(draft)


def append_evidence_record(
    record: EvidenceRecord,
    *,
    route_candidates: dict[str, RouteCandidate] | None = None,
    path: Path | None = None,
    draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
) -> ProviderImportDraft:
    """Append one evidence record without replacing older scoped evidence."""
    return _store(path).append_evidence_record(
        record,
        route_candidates=route_candidates,
        draft_id=draft_id,
    )


def new_evidence_id(prefix: str = "evidence") -> str:
    """Return a compact unique evidence ID."""
    return f"{prefix}-{uuid.uuid4().hex}"


def apply_draft(
    draft_id: str,
    *,
    path: Path | None = None,
    credentials_path: Path | None = None,
    conflict_mode: ConflictMode | None = None,
) -> ProviderImportDraft:
    """Apply endpoint and route candidates into active credentials."""
    store_path = path or drafts_path()
    active_path = credentials_path or default_credentials_path()
    store = ImportDraftStore(store_path)
    try:
        draft = store.load_draft(draft_id)
    except KeyError as exc:
        raise DraftNotFound(draft_id) from exc
    with _APPLY_LOCK:
        if _is_expired(draft):
            raise DraftExpired(draft_id)
        credentials = load_credentials(active_path)
        endpoint_collisions = sorted(
            endpoint_id for endpoint_id in draft.endpoint_candidates if endpoint_id in credentials.provider_endpoints
        )
        if endpoint_collisions and conflict_mode != "merge":
            raise DraftApplyConflict("active endpoints already exist: " + ", ".join(endpoint_collisions))
        try:
            materialized = materialize_import_draft_candidates(draft)
        except ValueError as exc:
            raise DraftApplyConflict(str(exc)) from exc
        route_collisions = sorted(
            route_id for route_id in materialized.provider_routes if route_id in credentials.provider_routes
        )
        if route_collisions and conflict_mode != "merge":
            raise DraftApplyConflict("active routes already exist: " + ", ".join(route_collisions))
        endpoints = dict(credentials.provider_endpoints)
        routes = dict(credentials.provider_routes)
        for endpoint_id, endpoint in materialized.provider_endpoints.items():
            endpoints[endpoint_id] = ProviderEndpoint.model_validate(
                {
                    **endpoint.model_dump(mode="python"),
                    "display_name": materialized.endpoint_display_names[endpoint_id],
                }
            )
        for route_id, route in materialized.provider_routes.items():
            routes[route_id] = ProviderRoute.model_validate(
                {
                    **route.model_dump(mode="python"),
                    "display_name": materialized.route_display_names.get(route_id),
                }
            )
        missing_endpoint_routes = sorted(
            route_id for route_id, route in routes.items() if route.endpoint_id not in endpoints
        )
        if missing_endpoint_routes:
            raise DraftApplyConflict(
                "routes reference missing endpoint: " + ", ".join(missing_endpoint_routes)
            )
        next_credentials = credentials.model_copy(update={"provider_endpoints": endpoints, "provider_routes": routes})
        save_credentials(next_credentials, active_path)
        try:
            return store.mark_draft_applied(draft_id)
        except KeyError as exc:
            raise DraftNotFound(draft_id) from exc


def _load_all(path: Path) -> dict[str, ProviderImportDraft]:
    return ImportDraftStore(path).load_all()


def _save_all(path: Path, drafts: dict[str, ProviderImportDraft]) -> None:
    ImportDraftStore(path).save_all(drafts)


def _is_expired(draft: ProviderImportDraft) -> bool:
    if draft.status == "expired":
        return True
    if not draft.expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(draft.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires_at <= datetime.now(tz=UTC)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _store(path: Path | None = None) -> ImportDraftStore:
    return ImportDraftStore(path or drafts_path())


logger = logging.getLogger(__name__)

DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/SevenX77/studio-llm-model-catalog/main/llm_import_drafts.json"


async def sync_remote_evidence_library(
    *,
    data: dict[str, Any] | None = None,
    url: str | None = None,
    path: Path | None = None,
    draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
) -> ProviderImportDraft:
    """Pull the remote evidence library and merge it into the local store."""
    target_url = url or os.getenv("STUDIO_CATALOG_URL") or DEFAULT_CATALOG_URL
    if data is None:
        logger.info("Syncing remote evidence library from %s", target_url)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(target_url)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.error("Failed to fetch remote evidence library: %s", exc)
            raise RemoteCatalogSyncError(f"failed to fetch remote evidence library from {target_url}: {exc}") from exc
    else:
        logger.info("Syncing remote evidence library from provided catalog payload")

    try:
        raw_drafts = data.get("drafts", data)
        if not isinstance(raw_drafts, dict):
            raise ValueError("Invalid remote draft payload structure")
        remote_draft_raw = raw_drafts.get(draft_id)
        if not remote_draft_raw:
            raise ValueError(f"remote evidence library not found for draft_id={draft_id}")
        remote_draft = ProviderImportDraft.model_validate(remote_draft_raw)
    except Exception as exc:
        logger.error("Failed to parse remote evidence library: %s", exc)
        raise RemoteCatalogSyncError(f"failed to parse remote evidence library from {target_url}: {exc}") from exc

    store_path = path or drafts_path()
    store = ImportDraftStore(store_path)
    local_record_ids = {
        record.evidence_id for record in store.load_evidence_library(draft_id=draft_id).evidence_records
    }
    updated = store.merge_evidence_library(remote_draft, draft_id=draft_id)
    new_records_count = sum(
        1 for record in updated.evidence_records if record.evidence_id not in local_record_ids
    )

    logger.info(
        "Merged remote drafts: new_records=%d, total_records=%d, total_routes=%d",
        new_records_count,
        len(updated.evidence_records),
        len(updated.route_candidates),
    )
    return updated


__all__ = [
    "DraftApplyConflict",
    "DraftExpired",
    "DraftNotFound",
    "EVIDENCE_LIBRARY_DRAFT_ID",
    "RemoteCatalogSyncError",
    "append_evidence_record",
    "apply_draft",
    "create_draft",
    "drafts_path",
    "load_evidence_library",
    "load_draft",
    "new_evidence_id",
    "save_draft",
    "sync_remote_evidence_library",
]
