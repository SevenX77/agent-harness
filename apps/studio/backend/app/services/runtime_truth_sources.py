"""Runtime truth-source catalogue shown in Studio General settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import config
from app.services.llm_paths import (
    canonical_rules_path,
    credentials_path,
    role_test_results_path,
    roles_path,
)
from app.services.runtime_activity import load_runtime_activity, runtime_activity_log_path

_MAX_CONTENT_BYTES = 256 * 1024
_TEXT_KINDS = {"json", "jsonl", "md", "txt", "yaml"}


@dataclass(frozen=True)
class TruthSource:
    id: str
    label: str
    path: Path
    kind: str
    description: str
    open_mode: str = "file"


@dataclass(frozen=True)
class TruthSourceSection:
    id: str
    label: str
    description: str
    sources: tuple[TruthSource, ...]


def build_truth_source_sections(*, log_limit_per_source: int = 8) -> dict[str, Any]:
    """Return grouped storage truth sources with file metadata and recent logs."""
    sections = [
        {
            "id": section.id,
            "label": section.label,
            "description": section.description,
            "sources": [
                _source_payload(source, log_limit=log_limit_per_source)
                for source in section.sources
            ],
        }
        for section in _truth_source_sections()
    ]
    return {"sections": sections}


def read_truth_source_content(source_id: str) -> dict[str, Any] | None:
    """Read a known text truth source for the in-app fallback viewer."""
    source = _truth_source_by_id().get(source_id)
    if source is None:
        return None
    if source.open_mode != "file" or source.kind not in _TEXT_KINDS:
        return None
    path = source.path
    if not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    truncated = stat.st_size > _MAX_CONTENT_BYTES
    with path.open("rb") as handle:
        raw = handle.read(_MAX_CONTENT_BYTES)
    content = raw.decode("utf-8", errors="replace")
    return {
        "source_id": source.id,
        "path": str(path),
        "kind": source.kind,
        "content": content,
        "truncated": truncated,
        "size_bytes": stat.st_size,
    }


def _truth_source_sections() -> tuple[TruthSourceSection, ...]:
    llm_health_path = credentials_path().with_name("llm_health.sqlite")
    return (
        TruthSourceSection(
            id="application",
            label="Application configuration",
            description="Studio-wide configuration and workspace roots.",
            sources=(
                TruthSource(
                    id="app_settings",
                    label="App settings",
                    path=config.APP_SETTINGS_PATH,
                    kind="json",
                    description=(
                        "Stores Studio UI preferences such as user id, default folder, "
                        "language, and remote catalog toggle."
                    ),
                ),
                TruthSource(
                    id="skill_index",
                    label="Skill index",
                    path=config.SKILL_INDEX_PATH,
                    kind="json",
                    description="Tracks indexed skills and workspace metadata used by the Studio shell.",
                ),
                TruthSource(
                    id="workspaces_root",
                    label="Workspaces root",
                    path=config.WORKSPACES_DIR,
                    kind="directory",
                    open_mode="directory",
                    description="Root directory for user workspaces and writable skill folders.",
                ),
                TruthSource(
                    id="default_skills_root",
                    label="Default skills root",
                    path=config.DEFAULT_SKILLS_ROOT,
                    kind="directory",
                    open_mode="directory",
                    description="Default writable skill root for the current local Studio profile.",
                ),
            ),
        ),
        TruthSourceSection(
            id="llm_runtime",
            label="LLM runtime truth",
            description="Credential, route, role, and health stores owned by the backend/gateway path.",
            sources=(
                TruthSource(
                    id="llm_credentials",
                    label="LLM credentials",
                    path=credentials_path(),
                    kind="json",
                    description=(
                        "The single source of truth for provider endpoints, API keys, "
                        "route status, and credential evidence references."
                    ),
                ),
                TruthSource(
                    id="llm_roles",
                    label="LLM roles",
                    path=roles_path(),
                    kind="yaml",
                    description=(
                        "Stores role definitions, model groups, and routing bundles used "
                        "by Studio runtime materialization."
                    ),
                ),
                TruthSource(
                    id="llm_role_test_results",
                    label="Role test results",
                    path=role_test_results_path(),
                    kind="json",
                    description="Persists role and copilot test outcomes shown by Studio diagnostics.",
                ),
                TruthSource(
                    id="llm_health",
                    label="LLM health database",
                    path=llm_health_path,
                    kind="sqlite",
                    description="Local health and cooldown diagnostics for provider routing.",
                ),
                TruthSource(
                    id="llm_canonical_rules",
                    label="Canonical model rules",
                    path=canonical_rules_path(),
                    kind="yaml",
                    description="Optional canonicalization rules for provider and model identities.",
                ),
            ),
        ),
        TruthSourceSection(
            id="diagnostics",
            label="Runtime diagnostics",
            description="Append-only diagnostics generated by Studio backend operations.",
            sources=(
                TruthSource(
                    id="runtime_activity_log",
                    label="Runtime activity log",
                    path=runtime_activity_log_path(),
                    kind="jsonl",
                    description=(
                        "Structured operation log used by General settings to show what ran, "
                        "when it ran, and what changed."
                    ),
                ),
            ),
        ),
    )


def _truth_source_by_id() -> dict[str, TruthSource]:
    return {
        source.id: source
        for section in _truth_source_sections()
        for source in section.sources
    }


def _source_payload(source: TruthSource, *, log_limit: int) -> dict[str, Any]:
    stat = _path_stat(source.path)
    return {
        "id": source.id,
        "label": source.label,
        "path": str(source.path),
        "kind": source.kind,
        "description": source.description,
        "open_mode": source.open_mode,
        "exists": stat["exists"],
        "size_bytes": stat["size_bytes"],
        "updated_at": stat["updated_at"],
        "logs": load_runtime_activity(source_id=source.id, limit=log_limit),
        "can_preview": source.kind in _TEXT_KINDS and source.open_mode == "file",
    }


def _path_stat(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size_bytes": None, "updated_at": None}
    stat = path.stat()
    updated_at = None
    try:
        updated_at = Path(path).stat().st_mtime
    except OSError:
        updated_at = None
    return {
        "exists": True,
        "size_bytes": stat.st_size if path.is_file() else None,
        "updated_at": _mtime_to_iso(updated_at),
    }


def _mtime_to_iso(mtime: float | None) -> str | None:
    if mtime is None:
        return None
    from datetime import datetime

    return datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds")


__all__ = [
    "build_truth_source_sections",
    "read_truth_source_content",
]
