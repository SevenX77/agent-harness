"""Gateway-owned import draft and evidence store contract."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from graph_agent_gateway.registry.base_url import canonicalize_base_url
from graph_agent_gateway.registry.schema import (
    EvidenceRecord,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RouteCandidate,
)

EVIDENCE_LIBRARY_DRAFT_ID = "studio-evidence-library"
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}


@dataclass(frozen=True)
class MaterializedImportDraftCandidates:
    provider_endpoints: dict[str, ProviderEndpoint]
    provider_routes: dict[str, ProviderRoute]
    endpoint_display_names: dict[str, str]
    route_display_names: dict[str, str]


class ImportDraftStore:
    """Atomic JSON store for provider import drafts and append-only evidence."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._write_lock = _lock_for_path(path)

    def load_all(self) -> dict[str, ProviderImportDraft]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"import draft store must contain an object: {self.path}")
        raw_drafts = payload.get("drafts", payload)
        if not isinstance(raw_drafts, dict):
            raise ValueError(f"import draft store drafts must be an object: {self.path}")
        return {
            str(draft_id): ProviderImportDraft.model_validate(draft)
            for draft_id, draft in raw_drafts.items()
        }

    def save_all(self, drafts: dict[str, ProviderImportDraft]) -> None:
        with self._write_lock:
            payload = {
                "drafts": {
                    draft_id: _draft_payload_for_storage(draft)
                    for draft_id, draft in sorted(drafts.items())
                }
            }
            serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                    tmp_file.write(serialized)
                    tmp_file.write("\n")
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                tmp_path.chmod(0o600)
                os.replace(tmp_path, self.path)
                self.path.chmod(0o600)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

    def save_draft(self, draft: ProviderImportDraft) -> ProviderImportDraft:
        with self._write_lock:
            drafts = self.load_all()
            drafts[draft.draft_id] = draft
            self.save_all(drafts)
        return draft

    def mutate_under_lock(
        self,
        mutator: Callable[[dict[str, ProviderImportDraft]], ProviderImportDraft],
    ) -> ProviderImportDraft:
        with self._write_lock:
            drafts = self.load_all()
            updated = mutator(drafts)
            self.save_all(drafts)
            return updated

    def mark_draft_applied(self, draft_id: str) -> ProviderImportDraft:
        def _mark(drafts: dict[str, ProviderImportDraft]) -> ProviderImportDraft:
            draft = drafts.get(draft_id)
            if draft is None:
                raise KeyError(draft_id)
            updated = draft.model_copy(update={"status": "applied"})
            drafts[draft_id] = updated
            return updated

        return self.mutate_under_lock(_mark)

    def load_draft(self, draft_id: str) -> ProviderImportDraft:
        draft = self.load_all().get(draft_id)
        if draft is None:
            raise KeyError(draft_id)
        return draft

    def load_evidence_library(
        self,
        *,
        draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
    ) -> ProviderImportDraft:
        return self.load_all().get(draft_id) or new_evidence_library(draft_id)

    def append_evidence_record(
        self,
        record: EvidenceRecord,
        *,
        route_candidates: dict[str, RouteCandidate] | None = None,
        draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
    ) -> ProviderImportDraft:
        now = _now_iso()
        record = record.model_copy(
            update={
                "observed_at": record.observed_at or now,
                "attempted_at": (
                    record.attempted_at or now
                    if record.evidence_type == "probe"
                    else record.attempted_at
                ),
            }
        )
        with self._write_lock:
            drafts = self.load_all()
            draft = drafts.get(draft_id) or new_evidence_library(draft_id, now=now)
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
            self.save_all(drafts)
            return updated

    def merge_evidence_library(
        self,
        remote: ProviderImportDraft,
        *,
        draft_id: str = EVIDENCE_LIBRARY_DRAFT_ID,
    ) -> ProviderImportDraft:
        with self._write_lock:
            drafts = self.load_all()
            local = drafts.get(draft_id) or new_evidence_library(draft_id)
            updated = merge_evidence_library(local, remote)
            drafts[draft_id] = updated
            self.save_all(drafts)
            return updated


def new_evidence_library(
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


def materialize_import_draft_candidates(
    draft: ProviderImportDraft,
) -> MaterializedImportDraftCandidates:
    provider_endpoints: dict[str, ProviderEndpoint] = {}
    endpoint_display_names: dict[str, str] = {}
    for endpoint_id, endpoint in draft.endpoint_candidates.items():
        endpoint_payload = endpoint.model_dump(
            mode="python",
            exclude={"display_name", "field_sources"},
        )
        endpoint_payload["base_url"] = canonicalize_base_url(
            endpoint.base_url,
            endpoint.protocol,
        )
        provider_endpoints[endpoint_id] = ProviderEndpoint.model_validate(endpoint_payload)
        endpoint_display_names[endpoint_id] = endpoint.display_name

    provider_routes: dict[str, ProviderRoute] = {}
    route_display_names: dict[str, str] = {}
    missing_endpoint_ids = sorted(
        {
            candidate.endpoint_id
            for candidate in draft.route_candidates.values()
            if candidate.endpoint_id not in provider_endpoints
        }
    )
    if missing_endpoint_ids:
        raise ValueError("missing endpoint candidates for routes: " + ", ".join(missing_endpoint_ids))
    for candidate in draft.route_candidates.values():
        route_id = f"{candidate.endpoint_id}:{candidate.route_slug}"
        provider_routes[route_id] = ProviderRoute(
            route_id=route_id,
            endpoint_id=candidate.endpoint_id,
            route_slug=candidate.route_slug,
            provider_model_id=candidate.provider_model_id,
            canonical_id=candidate.canonical_id,
            status="unverified_manual",
            capabilities=candidate.capabilities,
            metadata=candidate.metadata,
        )
        route_display_names[route_id] = candidate.display_name

    return MaterializedImportDraftCandidates(
        provider_endpoints=provider_endpoints,
        provider_routes=provider_routes,
        endpoint_display_names=endpoint_display_names,
        route_display_names=route_display_names,
    )


def merge_evidence_library(
    local: ProviderImportDraft,
    remote: ProviderImportDraft,
    *,
    now: str | None = None,
) -> ProviderImportDraft:
    merged_routes = dict(local.route_candidates)
    for route_id, route in remote.route_candidates.items():
        existing = merged_routes.get(route_id)
        if existing is None:
            merged_routes[route_id] = route
            continue
        merged_routes[route_id] = existing.model_copy(
            update={
                "capabilities": {
                    **existing.capabilities,
                    **route.capabilities,
                },
                "metadata": {
                    **existing.metadata,
                    **route.metadata,
                },
            }
        )

    local_evidence_ids = {record.evidence_id for record in local.evidence_records}
    merged_records = list(local.evidence_records)
    for record in remote.evidence_records:
        if record.evidence_id not in local_evidence_ids:
            merged_records.append(record)
            local_evidence_ids.add(record.evidence_id)

    return local.model_copy(
        update={
            "updated_at": now or _now_iso(),
            "route_candidates": merged_routes,
            "evidence_records": merged_records,
        }
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


def _lock_for_path(path: Path) -> threading.RLock:
    lock_key = path.expanduser().resolve(strict=False)
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(lock_key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[lock_key] = lock
        return lock
