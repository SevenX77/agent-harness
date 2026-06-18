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
    (".workspace", "test_inputs"),
    (".workspace", "golden"),
)
_SOURCE_ROOT_FILES = {"GRAPH.md", "SKILL.md"}
_SOURCE_ROOT_DIRS = {"phases", "io"}


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
