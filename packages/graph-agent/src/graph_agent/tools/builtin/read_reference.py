from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload


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
        detail = "reference_id must be a string"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-tool-argument-invalid]", detail),
        )
    spec = references.get(reference_id)
    if spec is None:
        detail = f"{reference_id!r}"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-resource-reference-not-found]", detail),
        )
    return read_resource_file(
        root=root,
        relative_path=getattr(spec, "path", ""),
        code="[F-v3-resource-reference-path-invalid]",
    )


def read_resource_file(*, root: Path, relative_path: str, code: str) -> str:
    if not isinstance(relative_path, str) or not relative_path:
        detail = "empty resource path"
        raise GraphAgentFatalError(detail, payload=make_error_payload(code, detail))
    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        detail = f"{relative_path!r} escapes skill root"
        raise GraphAgentFatalError(detail, payload=make_error_payload(code, detail))
    candidate = (root / raw_path).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        detail = f"{relative_path!r} escapes skill root"
        raise GraphAgentFatalError(detail, payload=make_error_payload(code, detail)) from exc
    if not candidate.is_file():
        detail = f"{relative_path!r} is not readable"
        raise GraphAgentFatalError(detail, payload=make_error_payload(code, detail))
    return candidate.read_text(encoding="utf-8")


__all__ = ["read_declared_reference", "read_resource_file"]
