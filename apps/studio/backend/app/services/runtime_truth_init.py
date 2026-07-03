"""Startup initialization for Studio runtime truth-source files."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from app.core import config
from app.models.llm_config import LLMCredentialsFile, RolesData
from app.models.settings import AppSettings
from app.services.llm_credentials import save_credentials
from app.services.llm_paths import (
    canonical_rules_path,
    credentials_path,
    role_test_results_path,
    roles_path,
)
from app.services.llm_roles import save_roles_file
from app.services.runtime_activity import record_runtime_activity, runtime_activity_log_path

logger = logging.getLogger(__name__)


def ensure_runtime_truth_sources() -> list[str]:
    """Create missing runtime truth-source files with safe empty contents."""
    created: list[tuple[str, Path]] = []

    _ensure_directory("workspaces_root", config.WORKSPACES_DIR, created)
    _ensure_directory("default_skills_root", config.DEFAULT_SKILLS_ROOT, created)
    _ensure_json_file("app_settings", config.APP_SETTINGS_PATH, AppSettings().model_dump(mode="json"), created)
    _ensure_json_file("skill_index", config.SKILL_INDEX_PATH, {}, created)
    _ensure_credentials_file(created)
    _ensure_roles_file(created)
    _ensure_fixed_roles(created)
    _ensure_json_file("llm_role_test_results", role_test_results_path(), {"results": {}}, created)
    # Phase 9: the three legacy catalog files (llm_probe_catalog.json /
    # community_catalog_cache.json / community_upload_queue.json) are retired — startup no
    # longer seeds them. Evidence lives in credentials route.evidence; community evidence
    # arrives via verified sync; uploads re-derive from credentials (no offline queue).
    _ensure_text_file("llm_canonical_rules", canonical_rules_path(), "{}\n", created)
    _ensure_text_file("runtime_activity_log", runtime_activity_log_path(), "", created)

    for source_id, path in created:
        record_runtime_activity(
            source_id=source_id,
            action="initialize_truth_source",
            message="Initialized missing runtime truth source during Studio startup.",
            changes={"path": str(path)},
        )
        logger.info(
            "runtime_truth_init action=initialize_truth_source source_id=%s path=%s",
            source_id,
            path,
        )

    if created:
        logger.info(
            "runtime_truth_init created %d truth source(s): %s",
            len(created),
            ", ".join(source_id for source_id, _path in created),
        )
    else:
        logger.info("runtime_truth_init checked runtime truth sources: all present")

    return [source_id for source_id, _path in created]


def _ensure_directory(source_id: str, path: Path, created: list[tuple[str, Path]]) -> None:
    if path.exists():
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append((source_id, path))


def _ensure_credentials_file(created: list[tuple[str, Path]]) -> None:
    path = credentials_path()
    if path.exists():
        return
    save_credentials(LLMCredentialsFile(), path)
    created.append(("llm_credentials", path))


def _ensure_roles_file(created: list[tuple[str, Path]]) -> None:
    path = roles_path()
    if path.exists():
        return
    save_roles_file(path, RolesData(), known_route_ids=set(), known_bundle_ids=set())
    created.append(("llm_roles", path))


def _ensure_fixed_roles(created: list[tuple[str, Path]]) -> None:
    """固定角色(引擎 builtin 硬依赖,如 md-patch 的 `fast`)必须始终在场:缺失就补一个
    空槽(用户在设置页填模型),不覆盖已存在的。这样即便迁移/重置清空了角色,固定角色
    也会在下次启动自动回来 —— 配合删除端点的守卫,构成"固定不可删"。"""
    from app.models.llm_config import RoleEntry
    from app.services.llm_fixed_roles import required_builtin_roles
    from app.services.llm_roles import load_roles_file

    required = required_builtin_roles()
    if not required:
        return
    path = roles_path()
    data = load_roles_file(path) if path.exists() else RolesData()
    missing = [name for name in required if name not in data.roles]
    if not missing:
        return
    roles = dict(data.roles)
    for name in missing:
        roles[name] = RoleEntry(role_kind="graph_agent")
    save_roles_file(
        path,
        data.model_copy(update={"roles": roles}),
        known_route_ids=set(),
        known_bundle_ids=set(),
    )
    created.append(("llm_roles_fixed", path))


def _ensure_json_file(
    source_id: str,
    path: Path,
    payload: Any,
    created: list[tuple[str, Path]],
) -> None:
    if path.exists():
        return
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    created.append((source_id, path))


def _ensure_text_file(
    source_id: str,
    path: Path,
    content: str,
    created: list[tuple[str, Path]],
) -> None:
    if path.exists():
        return
    _atomic_write_text(path, content)
    created.append((source_id, path))


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


__all__ = ["ensure_runtime_truth_sources"]
