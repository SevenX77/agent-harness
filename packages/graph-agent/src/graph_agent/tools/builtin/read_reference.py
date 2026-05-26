from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError


def read_declared_reference(
    *,
    root: Path,
    references: Mapping[str, Any],
    reference_id: Any,
    query: Any = "",
    mode: Any = "excerpt",
) -> str:
    del query, mode
    if not isinstance(reference_id, str) or not reference_id:
        raise GraphAgentFatalError("[F-v3-tool-argument-invalid] reference_id must be a string")
    spec = references.get(reference_id)
    if spec is None:
        raise GraphAgentFatalError(f"[F-v3-resource-reference-not-found] {reference_id!r}")
    return read_resource_file(
        root=root,
        relative_path=getattr(spec, "path", ""),
        error_code="[F-v3-resource-reference-path-invalid]",
    )


def read_resource_file(*, root: Path, relative_path: str, error_code: str) -> str:
    if not isinstance(relative_path, str) or not relative_path:
        raise GraphAgentFatalError(f"{error_code} empty resource path")
    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        raise GraphAgentFatalError(f"{error_code} {relative_path!r} escapes skill root")
    candidate = (root / raw_path).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise GraphAgentFatalError(f"{error_code} {relative_path!r} escapes skill root") from exc
    if not candidate.is_file():
        raise GraphAgentFatalError(f"{error_code} {relative_path!r} is not readable")
    return candidate.read_text(encoding="utf-8")


__all__ = ["read_declared_reference", "read_resource_file"]
