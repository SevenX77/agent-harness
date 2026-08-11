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
    CapabilityValue,
    EvidenceRecord,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RouteCandidate,
    VerifiedProfile,
)

EVIDENCE_LIBRARY_DRAFT_ID = "studio-evidence-library"
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}


@dataclass(frozen=True)
class MaterializedProbeCatalogCandidates:
    provider_endpoints: dict[str, ProviderEndpoint]
    provider_routes: dict[str, ProviderRoute]
    endpoint_display_names: dict[str, str]
    route_display_names: dict[str, str]


@dataclass(frozen=True)
class PromotableRouteUpdate:
    capabilities: dict[str, CapabilityValue]
    verified_profiles: list[VerifiedProfile]
    evidence_refs: list[str]


class ProbeCatalogStore:
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


def materialize_probe_catalog_candidates(
    draft: ProviderImportDraft,
) -> MaterializedProbeCatalogCandidates:
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
            status="unverified_manual",
            capabilities=candidate.capabilities,
            metadata=candidate.metadata,
        )
        route_display_names[route_id] = candidate.display_name

    return MaterializedProbeCatalogCandidates(
        provider_endpoints=provider_endpoints,
        provider_routes=provider_routes,
        endpoint_display_names=endpoint_display_names,
        route_display_names=route_display_names,
    )


def known_verified_capabilities(
    library: ProviderImportDraft,
    endpoint_id: str,
    model_id: str,
) -> dict[str, CapabilityValue]:
    """Return probe-verified capabilities previously observed for one model."""
    capabilities: dict[str, CapabilityValue] = {}
    for record in _probe_records_for_model(
        library,
        endpoint_id=endpoint_id,
        model_id=model_id,
        trust_state="probe-verified",
    ):
        capabilities.update(record.candidate_capabilities)
        if record.input_modalities and "input_modalities" not in capabilities:
            capabilities["input_modalities"] = CapabilityValue(
                value=list(record.input_modalities),
                source="probed_verified",
                observed_at=record.observed_at,
            )
        if record.output_modalities and "output_modalities" not in capabilities:
            capabilities["output_modalities"] = CapabilityValue(
                value=list(record.output_modalities),
                source="probed_verified",
                observed_at=record.observed_at,
            )
        if record.method_id:
            existing_methods = capabilities.get("verified_methods")
            method_values = (
                list(existing_methods.value)
                if existing_methods is not None and isinstance(existing_methods.value, list)
                else []
            )
            if record.method_id not in method_values:
                method_values.append(record.method_id)
            capabilities["verified_methods"] = CapabilityValue(
                value=method_values,
                source="probed_verified",
                observed_at=record.observed_at,
            )
    return capabilities


def known_model_ids_for_endpoint(
    library: ProviderImportDraft,
    endpoint_id: str,
) -> list[str]:
    """Return draft-known provider model ids for an endpoint in stable order."""
    model_ids: list[str] = []
    seen: set[str] = set()
    for route in library.route_candidates.values():
        if route.endpoint_id == endpoint_id and route.provider_model_id not in seen:
            model_ids.append(route.provider_model_id)
            seen.add(route.provider_model_id)
    for record in library.evidence_records:
        model_id = _record_model_id(record)
        if record.endpoint_id == endpoint_id and model_id and model_id not in seen:
            model_ids.append(model_id)
            seen.add(model_id)
    return model_ids


def probe_priority(
    library: ProviderImportDraft,
    endpoint_id: str,
    candidate_model_ids: list[str],
) -> list[str]:
    """Skip known-good probe models and put known failures after unknowns."""
    verified = _known_probe_model_ids(library, endpoint_id, "probe-verified")
    failed = _known_probe_model_ids(library, endpoint_id, "probe-failed")
    unknown_candidates: list[str] = []
    failed_candidates: list[str] = []
    for model_id in candidate_model_ids:
        if model_id in verified:
            continue
        if model_id in failed:
            failed_candidates.append(model_id)
            continue
        unknown_candidates.append(model_id)
    return [*unknown_candidates, *failed_candidates]


def promotable_route_update(
    library: ProviderImportDraft,
    route: ProviderRoute,
) -> PromotableRouteUpdate:
    """Derive credential-route capability/profile updates from verified draft evidence."""
    capabilities = known_verified_capabilities(
        library,
        route.endpoint_id,
        route.provider_model_id,
    )
    profiles: list[VerifiedProfile] = []
    evidence_refs: list[str] = []
    seen_profile_keys: set[tuple[str, str]] = set()
    for record in _probe_records_for_model(
        library,
        endpoint_id=route.endpoint_id,
        model_id=route.provider_model_id,
        trust_state="probe-verified",
    ):
        evidence_refs.append(record.evidence_id)
        if not record.method_id:
            continue
        request_mapper_id = record.request_mapper_id or record.method_id
        profile_key = (record.method_id, request_mapper_id)
        if profile_key in seen_profile_keys:
            continue
        seen_profile_keys.add(profile_key)
        profiles.append(
            VerifiedProfile(
                profile_id=record.method_id,
                capability=record.capability_family or record.model_type or "text_chat",
                method_id=record.method_id,
                request_mapper_id=request_mapper_id,
                status="ready",
                default=not profiles,
                fallback_rank=len(profiles) + 1,
                input_modalities=record.input_modalities or ["text"],
                output_modalities=record.output_modalities or ["text"],
                metadata={"evidence_id": record.evidence_id},
            )
        )
    return PromotableRouteUpdate(
        capabilities=capabilities,
        verified_profiles=profiles,
        evidence_refs=evidence_refs,
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


def _probe_records_for_model(
    library: ProviderImportDraft,
    *,
    endpoint_id: str,
    model_id: str,
    trust_state: str,
) -> list[EvidenceRecord]:
    return [
        record
        for record in library.evidence_records
        if record.evidence_type == "probe"
        and record.trust_state == trust_state
        and record.endpoint_id == endpoint_id
        and _record_model_id(record) == model_id
    ]


def _known_probe_model_ids(
    library: ProviderImportDraft,
    endpoint_id: str,
    trust_state: str,
) -> set[str]:
    return {
        model_id
        for record in library.evidence_records
        if record.evidence_type == "probe"
        and record.trust_state == trust_state
        and record.endpoint_id == endpoint_id
        if (model_id := _record_model_id(record)) is not None
    }


def _record_model_id(record: EvidenceRecord) -> str | None:
    return record.model_id or record.provider_model_id


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
