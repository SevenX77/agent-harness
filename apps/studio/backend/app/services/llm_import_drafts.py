"""Import-draft storage and append-only provider evidence records."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from graph_agent_gateway.registry.schema import (
    EvidenceRecord,
    ProviderImportDraft,
    RouteCandidate,
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

_WRITE_LOCK = threading.Lock()
EVIDENCE_LIBRARY_DRAFT_ID = "studio-evidence-library"

ConflictMode = Literal["merge"]


class DraftNotFound(KeyError):
    """Requested import draft does not exist."""


class DraftExpired(ValueError):
    """Import draft is expired and cannot be applied."""


class DraftApplyConflict(ValueError):
    """Import draft collides with active config and needs explicit choice."""


def drafts_path() -> Path:
    """Return the import draft and evidence store path."""
    return import_drafts_path()


def create_draft(
    draft: ProviderImportDraft,
    *,
    path: Path | None = None,
) -> ProviderImportDraft:
    """Create or replace one draft in the transient store."""
    save_draft(draft, path=path)
    return draft


def load_draft(draft_id: str, *, path: Path | None = None) -> ProviderImportDraft:
    """Load one draft or raise DraftNotFound."""
    drafts = _load_all(path or drafts_path())
    draft = drafts.get(draft_id)
    if draft is None:
        raise DraftNotFound(draft_id)
    return draft


def load_evidence_library(
    *,
    path: Path | None = None,
    draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
) -> ProviderImportDraft:
    """Load the durable evidence library, returning an empty one if absent."""
    drafts = _load_all(path or drafts_path())
    return drafts.get(draft_id) or _new_evidence_library(draft_id)


def save_draft(draft: ProviderImportDraft, *, path: Path | None = None) -> ProviderImportDraft:
    """Atomically save one draft."""
    store_path = path or drafts_path()
    with _WRITE_LOCK:
        drafts = _load_all(store_path)
        drafts[draft.draft_id] = draft
        _save_all(store_path, drafts)
    return draft


def append_evidence_record(
    record: EvidenceRecord,
    *,
    route_candidates: dict[str, RouteCandidate] | None = None,
    path: Path | None = None,
    draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
) -> ProviderImportDraft:
    """Append one evidence record without replacing older scoped evidence."""
    store_path = path or drafts_path()
    now = _now_iso()
    record = record.model_copy(
        update={
            "observed_at": record.observed_at or now,
            "attempted_at": record.attempted_at or now
            if record.evidence_type == "probe"
            else record.attempted_at,
        }
    )
    with _WRITE_LOCK:
        drafts = _load_all(store_path)
        draft = drafts.get(draft_id) or _new_evidence_library(draft_id, now=now)
        updated = draft.model_copy(
            update={
                "created_at": draft.created_at or now,
                "updated_at": now,
                "route_candidates": {
                    **draft.route_candidates,
                    **(route_candidates or {}),
                },
                "evidence_records": [*draft.evidence_records, record],
            }
        )
        drafts[draft_id] = updated
        _save_all(store_path, drafts)
        return updated


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
    with _WRITE_LOCK:
        drafts = _load_all(store_path)
        draft = drafts.get(draft_id)
        if draft is None:
            raise DraftNotFound(draft_id)
        if _is_expired(draft):
            raise DraftExpired(draft_id)
        credentials = load_credentials(active_path)
        collisions = sorted(
            endpoint_id
            for endpoint_id in draft.endpoint_candidates
            if endpoint_id in credentials.provider_endpoints
        )
        if collisions and conflict_mode != "merge":
            raise DraftApplyConflict(
                "active endpoints already exist: " + ", ".join(collisions)
            )
        endpoints = dict(credentials.provider_endpoints)
        routes = dict(credentials.provider_routes)
        for endpoint_id, endpoint in draft.endpoint_candidates.items():
            endpoints[endpoint_id] = ProviderEndpoint(
                endpoint_id=endpoint.endpoint_id,
                display_name=endpoint.display_name,
                protocol=endpoint.protocol,
                base_url=endpoint.base_url,
                api_key=endpoint.api_key,
                status=endpoint.status,
                last_test_at=endpoint.last_test_at,
                last_test_message=endpoint.last_test_message,
                provider_kind=endpoint.provider_kind,
                rate_limit_bucket=endpoint.rate_limit_bucket,
                timeout_seconds=endpoint.timeout_seconds,
                trust_env=endpoint.trust_env,
                proxy_env=endpoint.proxy_env,
                metadata=endpoint.metadata,
            )
        for route_id, candidate in draft.route_candidates.items():
            route = ProviderRoute(
                route_id=route_id,
                endpoint_id=candidate.endpoint_id,
                route_slug=candidate.route_slug,
                provider_model_id=candidate.provider_model_id,
                canonical_id=candidate.canonical_id,
                display_name=candidate.display_name,
                status="unverified_manual",
                capabilities=candidate.capabilities,
                metadata=candidate.metadata,
            )
            routes[route_id] = route
        next_credentials = credentials.model_copy(
            update={"provider_endpoints": endpoints, "provider_routes": routes}
        )
        save_credentials(next_credentials, active_path)
        updated = draft.model_copy(update={"status": "applied"})
        drafts[draft_id] = updated
        _save_all(store_path, drafts)
        return updated


def _load_all(path: Path) -> dict[str, ProviderImportDraft]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"import draft store must contain an object: {path}")
    raw_drafts = payload.get("drafts", payload)
    if not isinstance(raw_drafts, dict):
        raise ValueError(f"import draft store drafts must be an object: {path}")
    return {
        str(draft_id): ProviderImportDraft.model_validate(draft)
        for draft_id, draft in raw_drafts.items()
    }


def _save_all(path: Path, drafts: dict[str, ProviderImportDraft]) -> None:
    payload = {
        "drafts": {
            draft_id: _draft_payload_for_storage(draft)
            for draft_id, draft in sorted(drafts.items())
        }
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(serialized)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.chmod(0o600)
        os.replace(tmp_path, path)
        path.chmod(0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


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


def _new_evidence_library(
    draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
    *,
    now: str | None = None,
) -> ProviderImportDraft:
    timestamp = now or _now_iso()
    return ProviderImportDraft(
        draft_id=draft_id,
        source={"kind": "studio_evidence_library"},
        status="pending",
        created_at=timestamp,
        updated_at=timestamp,
    )


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _draft_payload_for_storage(draft: ProviderImportDraft) -> dict[str, object]:
    payload = draft.model_dump(mode="json")
    endpoint_candidates = payload.get("endpoint_candidates")
    if isinstance(endpoint_candidates, dict):
        for endpoint_id, endpoint in draft.endpoint_candidates.items():
            api_key = endpoint.api_key
            endpoint_payload = endpoint_candidates.get(endpoint_id)
            if isinstance(endpoint_payload, dict):
                endpoint_payload["api_key"] = (
                    api_key.get_secret_value() if api_key is not None else None
                )
    return payload


__all__ = [
    "DraftApplyConflict",
    "DraftExpired",
    "DraftNotFound",
    "EVIDENCE_LIBRARY_DRAFT_ID",
    "append_evidence_record",
    "apply_draft",
    "create_draft",
    "drafts_path",
    "load_evidence_library",
    "load_draft",
    "new_evidence_id",
    "save_draft",
]
