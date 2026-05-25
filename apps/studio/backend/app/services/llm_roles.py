"""Round-trip role configuration service for ``config/llm_roles.yaml``."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from app.models.llm_config import RoleEntry, RolesData
from app.services.migrations import migrate_roles_payload

_WRITE_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


class InvalidRoleReference(ValueError):
    """Raised when a role/model/provider reference is invalid."""


def load_roles_file(path: Path) -> RolesData:
    """Load an LLM roles YAML file with round-trip metadata attached."""

    text = path.read_text(encoding="utf-8")
    yaml = _yaml()
    raw = yaml.load(text)
    plain_before_migration = _plain(raw)
    plain = migrate_roles_payload(deepcopy(plain_before_migration))
    migrated = plain != plain_before_migration
    data = RolesData.model_validate(plain)
    data.migration_required = migrated
    if migrated:
        logger.warning(
            "llm_roles.yaml legacy schema migrated in memory; save to persist new format"
        )
    data._raw = raw
    data._original_text = None if migrated else text
    data._original_snapshot = None if migrated else data.model_dump(mode="json")
    return data


def save_roles_file(path: Path, data: RolesData) -> None:
    """Atomically save roles YAML, preserving unchanged round-trip text."""

    normalize_role_drafts(data)
    validate_references(data)
    if data._original_snapshot == data.model_dump(mode="json") and data._original_text is not None:
        serialized = data._original_text
    else:
        raw = data._raw if data._raw is not None else {}
        serialized = _dump_synced_raw(raw, data)
    _atomic_write(path, serialized)


def get_role(data: RolesData, role_name: str) -> RoleEntry:
    """Return one role entry or raise ``KeyError``."""

    return data.roles[role_name]


def validate_references(data: RolesData) -> None:
    """Validate role -> model -> provider references before writing."""

    for role_name, role in data.roles.items():
        if not role.models:
            if role.active_model:
                raise InvalidRoleReference(
                    f"role {role_name} has no models but active_model is set"
                )
            continue
        if role.active_model not in data.models:
            raise InvalidRoleReference(
                f"role {role_name} active_model references unknown model {role.active_model}"
            )
        if role.active_model not in role.models:
            raise InvalidRoleReference(
                f"role {role_name} active_model is not configured in this role"
            )
        for model_code, role_model in role.models.items():
            model = data.models.get(model_code)
            if model is None:
                raise InvalidRoleReference(
                    f"role {role_name} references unknown model {model_code}"
                )
            for provider_code in role_model.providers:
                if provider_code not in data.providers:
                    raise InvalidRoleReference(
                        f"role {role_name} model {model_code} references unknown provider "
                        f"{provider_code}"
                    )
                if provider_code not in model.providers:
                    raise InvalidRoleReference(
                        f"role {role_name} model {model_code} uses provider {provider_code}, "
                        "but model has no provider mapping"
                    )


def normalize_role_drafts(data: RolesData) -> None:
    """Clear stale active_model and orphan model values from draft roles."""

    for role in data.roles.values():
        for model_code in list(role.models.keys()):
            if model_code not in data.models:
                del role.models[model_code]
        if not role.models:
            role.active_model = ""
        elif role.active_model not in role.models or role.active_model not in data.models:
            role.active_model = next(iter(role.models))


def _dump_synced_raw(raw: Any, data: RolesData) -> str:
    payload = data.model_dump(
        mode="json",
        exclude_none=True,
        exclude={"migration_required"},
    )
    if raw is None or not isinstance(raw, dict):
        raw = {}
    raw["models"] = payload["models"]
    raw["providers"] = payload["providers"]
    raw["roles"] = payload["roles"]
    if "single_model_roles" in payload:
        raw["single_model_roles"] = payload["single_model_roles"]
    if "peer_model_groups" in payload:
        raw["peer_model_groups"] = payload["peer_model_groups"]
    if payload.get("circuit_breaker") is not None:
        raw["circuit_breaker"] = payload["circuit_breaker"]

    yaml = _yaml()
    buffer = StringIO()
    yaml.dump(raw, buffer)
    return buffer.getvalue()


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
    "save_roles_file",
    "validate_references",
]
