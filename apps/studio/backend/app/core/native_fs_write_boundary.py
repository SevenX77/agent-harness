"""Workspace write classification for the native-fs source writer boundary."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class WorkspaceWriteClassification:
    kind: str
    requires_native_fs_source_writer: bool


_RUNTIME_ARTIFACT_PREFIX = (".workspace", "runs")
_STUDIO_WORKSPACE_DATA_PREFIXES = (
    (".workspace", "import_files"),
    (".workspace", "golden"),
)
_SOURCE_ROOT_FILES = {"GRAPH.md", "SKILL.md"}
_SOURCE_ROOT_DIRS = {"phases", "io"}

SKILL_FILE_SOURCE_WRITE_ROUTE = (
    "POST",
    "/api/skills/{skill_id}/files/{file_path:path}",
)
FULL_SKILL_SOURCE_WRITE_ROUTE = (
    "PUT",
    "/api/skills/{skill_id}",
)

NATIVE_FS_SOURCE_WRITE_ROUTE_ALLOWLIST = {
    SKILL_FILE_SOURCE_WRITE_ROUTE: {
        "owner": "D12/native-fs",
        "reason": "Browser-only fallback for source file saves when Tauri native-fs is unavailable.",
        "risk": "Python FastAPI fallback can bypass Rust native-fs unless guarded by explicit header and tests.",
        "expiry": (
            "Remove after browser authoring fallback is retired or replaced by a native-fs-equivalent "
            "backend contract."
        ),
        "gate": "apps/studio/backend/tests/routers/test_skill_file_native_fs_guard_red.py",
        "fallback_header": "X-Studio-Write-Fallback",
        "fallback_value": "browser",
    },
    FULL_SKILL_SOURCE_WRITE_ROUTE: {
        "owner": "D12/native-fs",
        "reason": "Legacy full skill map update surface retained for backend compatibility tests.",
        "risk": "Whole-skill Python rewrites can bypass Rust native-fs if production clients start using this route.",
        "expiry": "Delete or convert to explicit browser fallback before D12 is marked fully closed.",
        "gate": "apps/studio/backend/tests/routers/test_skill_file_native_fs_guard_red.py",
        "fallback_header": "X-Studio-Write-Fallback",
        "fallback_value": "browser",
    },
}


def native_fs_source_write_route_metadata(route_key: tuple[str, str]) -> dict[str, str]:
    metadata = NATIVE_FS_SOURCE_WRITE_ROUTE_ALLOWLIST[route_key]
    return {str(key): str(value) for key, value in metadata.items()}


def source_write_fallback_header(route_key: tuple[str, str]) -> str:
    return native_fs_source_write_route_metadata(route_key)["fallback_header"]


def source_write_fallback_value(route_key: tuple[str, str]) -> str:
    return native_fs_source_write_route_metadata(route_key)["fallback_value"]


def classify_workspace_write_path(path: str | Path) -> WorkspaceWriteClassification:
    parts = _path_parts(path)
    if ".." in parts:
        return WorkspaceWriteClassification(
            kind="invalid_path",
            requires_native_fs_source_writer=False,
        )
    if parts[:2] == _RUNTIME_ARTIFACT_PREFIX:
        return WorkspaceWriteClassification(
            kind="runtime_artifact",
            requires_native_fs_source_writer=False,
        )
    if parts[:2] in _STUDIO_WORKSPACE_DATA_PREFIXES:
        return WorkspaceWriteClassification(
            kind="studio_workspace_data",
            requires_native_fs_source_writer=True,
        )
    if parts and (parts[0] in _SOURCE_ROOT_FILES or parts[0] in _SOURCE_ROOT_DIRS):
        return WorkspaceWriteClassification(
            kind="source_file",
            requires_native_fs_source_writer=True,
        )
    return WorkspaceWriteClassification(
        kind="other",
        requires_native_fs_source_writer=False,
    )


def collect_native_fs_source_writer_candidates(path: Path) -> list[str]:
    """Return source-like string literals that may need native-fs review."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    candidates: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        classification = classify_workspace_write_path(node.value)
        if classification.requires_native_fs_source_writer:
            candidates.append(
                f"{path}:{node.lineno} source-writer candidate literal {node.value!r}"
            )
    return candidates


def _path_parts(path: str | Path) -> tuple[str, ...]:
    raw_path = str(path).replace("\\", "/")
    return tuple(
        part for part in PurePosixPath(raw_path).parts if part not in {"", ".", "/"}
    )
