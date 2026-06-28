"""Startup initialization for Studio runtime truth-source files."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from graph_agent_gateway.import_draft_store import ImportDraftStore

from app.core import config
from app.models.llm_config import LLMCredentialsFile, RolesData
from app.models.settings import AppSettings
from app.services.community_catalog_sync import (
    CommunityCatalogCache,
    DisposableCatalogCacheStore,
)
from app.services.community_catalog_upload import OfflineUploadQueue
from app.services.llm_credentials import save_credentials
from app.services.llm_paths import (
    canonical_rules_path,
    community_catalog_cache_path,
    community_upload_queue_path,
    credentials_path,
    probe_catalog_path,
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
    _ensure_json_file("llm_role_test_results", role_test_results_path(), {"results": {}}, created)
    _ensure_probe_catalog_file(created)
    _ensure_community_catalog_cache_file(created)
    _ensure_upload_queue_file(created)
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


def _ensure_probe_catalog_file(created: list[tuple[str, Path]]) -> None:
    path = probe_catalog_path()
    if path.exists():
        return
    store = ImportDraftStore(path)
    draft = store.load_evidence_library()
    store.save_all({draft.draft_id: draft})
    created.append(("llm_probe_catalog", path))


def _ensure_community_catalog_cache_file(created: list[tuple[str, Path]]) -> None:
    path = community_catalog_cache_path()
    if path.exists():
        return
    DisposableCatalogCacheStore(path).save(CommunityCatalogCache())
    created.append(("community_catalog_cache", path))


def _ensure_upload_queue_file(created: list[tuple[str, Path]]) -> None:
    path = community_upload_queue_path()
    if path.exists():
        return
    OfflineUploadQueue(path).replace([])
    created.append(("community_upload_queue", path))


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
