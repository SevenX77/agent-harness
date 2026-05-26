"""Round-trip storage for v2 route-chain ``llm_roles.yaml``."""

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


def load_roles_file(path: Path) -> RolesData:
    """Load a v2 roles YAML file; legacy short-code schemas are fatal."""
    payload = _yaml().load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"llm_roles.yaml must contain a mapping: {path}")
    _reject_legacy_roles(payload, path)
    return RolesData.model_validate(_plain(payload))


def save_roles_file(
    path: Path,
    data: RolesData,
    *,
    known_route_ids: set[str] | None = None,
) -> None:
    """Atomically save roles YAML after route reference validation."""
    validate_references(data, known_route_ids=known_route_ids)
    payload = _quote_lint_values(data.model_dump(mode="json"))
    yaml = _yaml()
    from io import StringIO

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
    for profile_id, profile in data.model_profiles.items():
        for index, entry in enumerate(profile.fallback_chain):
            if entry.route_id not in known_route_ids:
                raise InvalidRoleReference(
                    f"profile {profile_id} fallback_chain[{index}] references unknown route "
                    f"{entry.route_id}"
                )


def normalize_role_drafts(data: RolesData) -> None:
    """V2 roles need no draft normalization; kept as explicit no-op."""
    del data


def _reject_legacy_roles(payload: dict[str, Any], path: Path) -> None:
    if payload.get("schema_version") != 2:
        raise ValueError(
            f"llm_roles.yaml must use schema_version 2; legacy short-code schema "
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
