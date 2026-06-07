"""Round-trip storage for Studio route-chain ``llm_roles.yaml``."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from app.models.llm_config import RoleEntry, RolesData
from app.services.llm_paths import roles_path

_WRITE_LOCK = threading.Lock()


class InvalidRoleReference(ValueError):
    """Raised when a role/profile references an unknown route."""


def _normalize_route_id(route_id: Any) -> Any:
    if not isinstance(route_id, str):
        return route_id
    import re
    return re.sub(r"\b(claude-(?:sonnet|opus|haiku)-\d+)-(\d+)\b", r"\1.\2", route_id)


def _normalize_payload(val: Any) -> Any:
    if isinstance(val, dict):
        result: dict[Any, Any] = {}
        for k, v in val.items():
            if k == "route_id" and isinstance(v, str):
                result[k] = _normalize_route_id(v)
            elif k == "route_ids" and isinstance(v, list):
                result[k] = [_normalize_route_id(item) for item in v]
            else:
                result[k] = _normalize_payload(v)
        return result
    if isinstance(val, list):
        return [_normalize_payload(item) for item in val]
    return val


def load_roles_file(path: Path) -> RolesData:
    """Load a roles YAML file; legacy short-code schemas are fatal."""
    payload = _yaml().load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"llm_roles.yaml must contain a mapping: {path}")
    _reject_legacy_roles(payload, path)
    normalized_payload = _normalize_payload(payload)
    return RolesData.model_validate(_plain(normalized_payload))



def save_roles_file(
    path: Path,
    data: RolesData,
    *,
    known_route_ids: set[str] | None = None,
) -> None:
    """Atomically save roles YAML after route reference validation."""
    validate_references(data, known_route_ids=known_route_ids)
    payload = _quote_lint_values(
        data.model_dump(mode="json", exclude=_runtime_response_exclude(data))
    )
    yaml = _yaml()
    from io import StringIO

    from app.services.file_watcher import record_api_write
    try:
        record_api_write(path)
    except Exception:
        pass

    buffer = StringIO()
    yaml.dump(payload, buffer)
    _atomic_write(path, buffer.getvalue())


def get_role(data: RolesData, role_name: str) -> RoleEntry:
    """Return one role entry or raise KeyError."""
    return data.roles[role_name]


def validate_references(
    data: RolesData,
    *,
    known_route_ids: set[str] | None = None,
) -> None:
    """Validate all role/profile route references against known routes."""
    if known_route_ids is None:
        return
    for role_name, role in data.roles.items():
        for index, entry in enumerate(role.fallback_chain):
            if entry.route_id not in known_route_ids:
                raise InvalidRoleReference(
                    f"role {role_name} fallback_chain[{index}] references unknown route "
                    f"{entry.route_id}"
                )
        for group_index, group in enumerate(role.model_groups):
            for provider_index, provider_model in enumerate(group.provider_models):
                if provider_model.route_id not in known_route_ids:
                    raise InvalidRoleReference(
                        f"role {role_name} model_groups[{group_index}]"
                        f".provider_models[{provider_index}] references unknown route "
                        f"{provider_model.route_id}"
                    )
    for profile_id, profile in data.model_profiles.items():
        for index, entry in enumerate(profile.fallback_chain):
            if entry.route_id not in known_route_ids:
                raise InvalidRoleReference(
                    f"profile {profile_id} fallback_chain[{index}] references unknown route "
                    f"{entry.route_id}"
                )
    for bundle_id, bundle in data.model_bundles.items():
        for index, entry in enumerate(bundle.fallback_chain):
            if entry.route_id not in known_route_ids:
                raise InvalidRoleReference(
                    f"model bundle {bundle_id} fallback_chain[{index}] references unknown route "
                    f"{entry.route_id}"
                )
        for group_index, group in enumerate(bundle.model_groups):
            for provider_index, provider_model in enumerate(group.provider_models):
                if provider_model.route_id not in known_route_ids:
                    raise InvalidRoleReference(
                        f"model bundle {bundle_id} model_groups[{group_index}]"
                        f".provider_models[{provider_index}] references unknown route "
                        f"{provider_model.route_id}"
                    )


def normalize_role_drafts(data: RolesData) -> None:
    """V2 roles need no draft normalization; kept as explicit no-op."""
    del data


def _reject_legacy_roles(payload: dict[str, Any], path: Path) -> None:
    if payload.get("schema_version") not in (2, 3):
        raise ValueError(
            f"llm_roles.yaml must use schema_version 2 or 3; legacy short-code schema "
            f"is rejected at the v2 cutover boundary: {path}"
        )
    legacy = {
        "models",
        "providers",
        "single_model_roles",
        "peer_model_groups",
        "circuit_breaker",
    }.intersection(payload)
    if legacy:
        raise ValueError(f"legacy roles fields are not supported: {sorted(legacy)}")
    for role_name, role in (payload.get("roles") or {}).items():
        if isinstance(role, dict) and ("active_model" in role or "models" in role):
            raise ValueError(f"legacy role schema is not supported for role: {role_name}")


def _quote_lint_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "lint_requirements" and isinstance(item, dict):
                result[key] = {
                    lint_key: DoubleQuotedScalarString(str(lint_value))
                    for lint_key, lint_value in item.items()
                }
            else:
                result[key] = _quote_lint_values(item)
        return result
    if isinstance(value, list):
        return [_quote_lint_values(item) for item in value]
    return value


def _runtime_response_exclude(data: RolesData) -> dict[str, Any]:
    """Exclude response-only materializer diagnostics from persisted authoring data."""
    return {
        "roles": {
            role_name: {"materialization_report"}
            for role_name in data.roles
        },
        "model_bundles": {
            bundle_id: {"materialization_report"}
            for bundle_id in data.model_bundles
        },
    }


def _atomic_write(path: Path, text: str) -> None:
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(text)
                if text and not text.endswith("\n"):
                    tmp_file.write("\n")
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


__all__ = [
    "InvalidRoleReference",
    "get_role",
    "load_roles_file",
    "normalize_role_drafts",
    "roles_path",
    "save_roles_file",
    "validate_references",
]
