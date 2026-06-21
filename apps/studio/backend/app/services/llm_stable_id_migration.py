"""Hard migration from random custom LLM ids to URL-stable route ids."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graph_agent_gateway.import_draft_store import ImportDraftStore
from graph_agent_gateway.registry.route_identity import route_slug, stable_endpoint_id

from app.models.llm_config import LLMCredentialsFile, ProviderImportDraft, RolesData
from app.services.llm_credentials import load_credentials, save_credentials
from app.services.llm_role_test_results import load_all as load_role_test_results
from app.services.llm_roles import load_roles_file, save_roles_file

_LEGACY_ENDPOINT_SPECS = {
    "openrouter-prod": ("anthropic_compatible", "https://openrouter.ai/api"),
    "qiniu-anthropic": ("anthropic_compatible", "https://anthropic.qnaigc.com"),
    "qiniu-openai": ("openai_compatible", "https://api.qnaigc.com/v1"),
    "wavespeed-prod": ("anthropic_compatible", "https://llm.wavespeed.ai/v1"),
    "onechats-anthropic": ("anthropic_compatible", "https://chatapi.onechats.ai/v1"),
    "onechats-openai": ("openai_compatible", "https://chatapi.onechats.ai/v1"),
}


@dataclass(frozen=True)
class StableRouteIdMigrationReport:
    endpoint_id_map: dict[str, str]
    route_id_map: dict[str, str]
    changed: bool


def migrate_llm_stable_route_ids(
    *,
    credentials_path: Path,
    roles_path: Path,
    import_drafts_path: Path,
    role_test_results_path: Path,
    health_db_path: Path,
) -> StableRouteIdMigrationReport:
    """Rewrite active LLM stores so custom endpoints use URL-derived ids only."""

    credentials = load_credentials(credentials_path)
    endpoint_id_map = _build_endpoint_id_map(credentials)
    endpoint_id_map = {**_legacy_endpoint_id_map(), **endpoint_id_map}
    endpoint_id_map.update(
        _draft_fingerprint_endpoint_id_map(import_drafts_path, credentials, endpoint_id_map)
    )
    route_id_map = _build_route_id_map(credentials, endpoint_id_map)
    migrated_credentials = _migrate_credentials(credentials, endpoint_id_map, route_id_map)
    migrated_roles = _load_migrated_roles(roles_path, endpoint_id_map, route_id_map)
    migrated_drafts = _load_migrated_import_drafts(import_drafts_path, endpoint_id_map, route_id_map)
    migrated_results = _load_migrated_role_test_results(
        role_test_results_path,
        endpoint_id_map,
        route_id_map,
    )
    changed = (
        migrated_credentials != credentials
        or _roles_changed(roles_path, migrated_roles)
        or _import_drafts_changed(import_drafts_path, migrated_drafts)
        or _role_test_results_changed(role_test_results_path, migrated_results)
        or _health_store_needs_migration(health_db_path, endpoint_id_map, route_id_map)
    )
    report = StableRouteIdMigrationReport(
        endpoint_id_map=endpoint_id_map,
        route_id_map=route_id_map,
        changed=changed,
    )
    if not changed:
        return report

    _backup_existing_paths(
        credentials_path,
        roles_path,
        import_drafts_path,
        role_test_results_path,
        health_db_path,
    )

    save_credentials(migrated_credentials, credentials_path)
    _save_migrated_roles(roles_path, migrated_roles)
    _save_migrated_import_drafts(import_drafts_path, migrated_drafts)
    _save_migrated_role_test_results(role_test_results_path, migrated_results)
    _migrate_health_store(health_db_path, endpoint_id_map, route_id_map)
    return report


def _build_endpoint_id_map(credentials: LLMCredentialsFile) -> dict[str, str]:
    endpoint_id_map: dict[str, str] = {}
    for endpoint_id, endpoint in credentials.provider_endpoints.items():
        if endpoint.provider_kind == "official":
            continue
        next_endpoint_id = stable_endpoint_id(
            protocol=endpoint.protocol,
            base_url=endpoint.base_url,
        )
        if next_endpoint_id != endpoint_id:
            endpoint_id_map[endpoint_id] = next_endpoint_id
    _assert_no_duplicate_targets(endpoint_id_map, "endpoint")
    return endpoint_id_map


def _build_route_id_map(
    credentials: LLMCredentialsFile,
    endpoint_id_map: dict[str, str],
) -> dict[str, str]:
    route_id_map: dict[str, str] = {}
    for route_id, route in credentials.provider_routes.items():
        endpoint_id = endpoint_id_map.get(route.endpoint_id, route.endpoint_id)
        next_route_slug = route_slug(route.provider_model_id)
        next_route_id = f"{endpoint_id}:{next_route_slug}"
        if next_route_id != route_id:
            route_id_map[route_id] = next_route_id
    _assert_no_duplicate_targets(route_id_map, "route")
    return route_id_map


def _legacy_endpoint_id_map() -> dict[str, str]:
    return {
        old_endpoint_id: stable_endpoint_id(protocol=protocol, base_url=base_url)
        for old_endpoint_id, (protocol, base_url) in _LEGACY_ENDPOINT_SPECS.items()
    }


def _draft_fingerprint_endpoint_id_map(
    path: Path,
    credentials: LLMCredentialsFile,
    endpoint_id_map: dict[str, str],
) -> dict[str, str]:
    if not path.exists():
        return {}
    fingerprint_targets: dict[str, set[str]] = {}
    for endpoint_id, endpoint in credentials.provider_endpoints.items():
        fingerprint = _base_url_fingerprint(endpoint.base_url)
        target_endpoint_id = endpoint_id_map.get(endpoint_id, endpoint_id)
        fingerprint_targets.setdefault(fingerprint, set()).add(target_endpoint_id)
    for legacy_endpoint_id, (_protocol, base_url) in _LEGACY_ENDPOINT_SPECS.items():
        target_endpoint_id = endpoint_id_map.get(legacy_endpoint_id)
        if target_endpoint_id is None:
            continue
        fingerprint_targets.setdefault(_base_url_fingerprint(base_url), set()).add(target_endpoint_id)
    unique_fingerprint_targets = {
        fingerprint: next(iter(targets))
        for fingerprint, targets in fingerprint_targets.items()
        if len(targets) == 1
    }

    inferred: dict[str, str] = {}
    for draft in ImportDraftStore(path).load_all().values():
        for record in draft.evidence_records:
            endpoint_id = record.endpoint_id
            if not endpoint_id or endpoint_id in endpoint_id_map:
                continue
            observation = record.model_list_observation
            if not isinstance(observation, dict):
                continue
            fingerprint = observation.get("base_url_fingerprint")
            if not isinstance(fingerprint, str):
                continue
            target_endpoint_id = unique_fingerprint_targets.get(fingerprint)
            if target_endpoint_id is not None and target_endpoint_id != endpoint_id:
                inferred[endpoint_id] = target_endpoint_id
    return inferred


def _base_url_fingerprint(base_url: str) -> str:
    return hashlib.sha256(base_url.rstrip("/").encode("utf-8")).hexdigest()[:16]


def _migrate_credentials(
    credentials: LLMCredentialsFile,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> LLMCredentialsFile:
    endpoints = {}
    for endpoint_id, endpoint in credentials.provider_endpoints.items():
        next_endpoint_id = endpoint_id_map.get(endpoint_id, endpoint_id)
        endpoints[next_endpoint_id] = endpoint.model_copy(
            update={
                "endpoint_id": next_endpoint_id,
                "rate_limit_bucket": endpoint_id_map.get(endpoint.rate_limit_bucket or "", endpoint.rate_limit_bucket),
                "metadata": _replace_ids(endpoint.metadata, endpoint_id_map, route_id_map),
            }
        )

    routes = {}
    for route_id, route in credentials.provider_routes.items():
        next_endpoint_id = endpoint_id_map.get(route.endpoint_id, route.endpoint_id)
        next_route_slug = route_slug(route.provider_model_id)
        next_route_id = route_id_map.get(route_id, f"{next_endpoint_id}:{next_route_slug}")
        routes[next_route_id] = route.model_copy(
            update={
                "route_id": next_route_id,
                "endpoint_id": next_endpoint_id,
                "route_slug": next_route_slug,
                "metadata": _replace_ids(route.metadata, endpoint_id_map, route_id_map),
            }
        )

    return credentials.model_copy(update={"provider_endpoints": endpoints, "provider_routes": routes})


def _load_migrated_roles(
    path: Path,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> RolesData | None:
    if not path.exists():
        return None
    roles = load_roles_file(path)
    payload = _replace_ids(roles.model_dump(mode="python"), endpoint_id_map, route_id_map)
    return RolesData.model_validate(payload)


def _save_migrated_roles(path: Path, roles: RolesData | None) -> None:
    if roles is None:
        return
    save_roles_file(
        path,
        roles,
        known_route_ids=None,
        known_bundle_ids=set(roles.model_bundles),
    )


def _roles_changed(path: Path, migrated: RolesData | None) -> bool:
    if migrated is None:
        return False
    return migrated != load_roles_file(path)


def _load_migrated_import_drafts(
    path: Path,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> dict[str, ProviderImportDraft] | None:
    if not path.exists():
        return None
    store = ImportDraftStore(path)
    drafts = store.load_all()
    return {
        draft_id: _migrate_import_draft(draft, endpoint_id_map, route_id_map)
        for draft_id, draft in drafts.items()
    }


def _save_migrated_import_drafts(
    path: Path,
    drafts: dict[str, ProviderImportDraft] | None,
) -> None:
    if drafts is None:
        return
    ImportDraftStore(path).save_all(drafts)


def _import_drafts_changed(path: Path, migrated: dict[str, ProviderImportDraft] | None) -> bool:
    if migrated is None:
        return False
    return migrated != ImportDraftStore(path).load_all()


def _migrate_import_draft(
    draft: ProviderImportDraft,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> ProviderImportDraft:
    payload = _replace_ids(draft.model_dump(mode="python"), endpoint_id_map, route_id_map)
    return ProviderImportDraft.model_validate(payload)


def _load_migrated_role_test_results(
    path: Path,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> dict[str, dict[str, Any]] | None:
    if not path.exists():
        return None
    results = load_role_test_results(path=path)
    return _replace_ids(results, endpoint_id_map, route_id_map)


def _save_migrated_role_test_results(
    path: Path,
    results: dict[str, dict[str, Any]] | None,
) -> None:
    if results is None:
        return
    _atomic_write_json(path, {"results": dict(sorted(results.items()))})


def _role_test_results_changed(path: Path, migrated: dict[str, dict[str, Any]] | None) -> bool:
    if migrated is None:
        return False
    return migrated != load_role_test_results(path=path)


def _health_store_needs_migration(
    path: Path,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> bool:
    if not path.exists():
        return False
    with sqlite3.connect(path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if "runtime_circuits" not in existing_tables:
            return False
        for old_route_id in route_id_map:
            found = conn.execute(
                "SELECT 1 FROM runtime_circuits WHERE scope = 'route' AND scope_id = ? LIMIT 1",
                (old_route_id,),
            ).fetchone()
            if found is not None:
                return True
        for old_endpoint_id in endpoint_id_map:
            found = conn.execute(
                """
                SELECT 1 FROM runtime_circuits
                WHERE scope IN ('endpoint', 'rate_limit_bucket') AND scope_id = ?
                LIMIT 1
                """,
                (old_endpoint_id,),
            ).fetchone()
            if found is not None:
                return True
    return False


def _migrate_health_store(
    path: Path,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> None:
    if not path.exists():
        return
    with sqlite3.connect(path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if "runtime_circuits" not in existing_tables:
            return
        for old_route_id, new_route_id in route_id_map.items():
            conn.execute(
                "UPDATE runtime_circuits SET scope_id = ? WHERE scope = 'route' AND scope_id = ?",
                (new_route_id, old_route_id),
            )
        for old_endpoint_id, new_endpoint_id in endpoint_id_map.items():
            conn.execute(
                "UPDATE runtime_circuits SET scope_id = ? WHERE scope = 'endpoint' AND scope_id = ?",
                (new_endpoint_id, old_endpoint_id),
            )
            conn.execute(
                "UPDATE runtime_circuits SET scope_id = ? WHERE scope = 'rate_limit_bucket' AND scope_id = ?",
                (new_endpoint_id, old_endpoint_id),
            )


def _replace_ids(
    value: Any,
    endpoint_id_map: dict[str, str],
    route_id_map: dict[str, str],
) -> Any:
    if isinstance(value, str):
        if value in route_id_map:
            return route_id_map[value]
        if value in endpoint_id_map:
            return endpoint_id_map[value]
        return _normalize_route_id_reference(value, endpoint_id_map)
    if isinstance(value, list):
        return [_replace_ids(item, endpoint_id_map, route_id_map) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_ids(item, endpoint_id_map, route_id_map) for item in value)
    if isinstance(value, dict):
        return {
            _replace_ids(key, endpoint_id_map, route_id_map): _replace_ids(
                item,
                endpoint_id_map,
                route_id_map,
            )
            for key, item in value.items()
        }
    return value


def _normalize_route_id_reference(value: str, endpoint_id_map: dict[str, str]) -> str:
    if ":" not in value:
        return value
    endpoint_id, route_part = value.split(":", 1)
    if not endpoint_id or not route_part:
        return value
    next_endpoint_id = endpoint_id_map.get(endpoint_id, endpoint_id)
    next_route_slug = route_slug(route_part)
    if next_endpoint_id == endpoint_id and next_route_slug == route_part:
        return value
    return f"{next_endpoint_id}:{next_route_slug}"


def _assert_no_duplicate_targets(mapping: dict[str, str], label: str) -> None:
    targets = list(mapping.values())
    if len(set(targets)) != len(targets):
        duplicates = sorted({target for target in targets if targets.count(target) > 1})
        raise ValueError(f"stable {label} id migration target collision: {', '.join(duplicates)}")


def _backup_existing_paths(*paths: Path) -> None:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    for path in paths:
        if not path.exists():
            continue
        backup_path = path.with_name(f"{path.name}.stable-id-migration.{timestamp}.bak")
        shutil.copy2(path, backup_path)
        try:
            backup_path.chmod(0o600)
        except OSError:
            pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


__all__ = ["StableRouteIdMigrationReport", "migrate_llm_stable_route_ids"]
