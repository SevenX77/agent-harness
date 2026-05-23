"""V0.3.0 builtin read_reference tool."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.manifest import ReferenceSpec


class ReadReferenceArgs(BaseModel):
    reference_id: str
    query: str = ""
    mode: Literal["excerpt", "full"] = "excerpt"


def build_read_reference_tool(
    *,
    skill_root: Path,
    references: list[ReferenceSpec],
) -> object:
    by_id = {item.id: item for item in references}

    def read_reference(reference_id: str, query: str = "", mode: str = "excerpt") -> str:
        spec = by_id.get(reference_id)
        if spec is None:
            raise GraphAgentFatalError(
                f"[F-v3-resource-reference-not-found] {reference_id!r}"
            )
        if mode not in {"excerpt", "full"}:
            raise GraphAgentFatalError(f"[F-v3-tool-argument-invalid] mode={mode!r}")
        content = _read_skill_root_file(skill_root, spec.path)
        body = content if mode == "full" else _excerpt(content)
        query_line = f"\n\nQuery: {query}" if query else ""
        return f"# Reference {spec.id}: {spec.summary}{query_line}\n\n{body}"

    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=read_reference,
        name="read_reference",
        description="Read a reference registered on the current Agent phase.",
        args_schema=ReadReferenceArgs,
    )


def _read_skill_root_file(root: Path, relative_path: str) -> str:
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise GraphAgentFatalError(
            f"[F-v3-resource-reference-path-invalid] {relative_path!r} escapes skill root"
        ) from exc
    if not candidate.is_file():
        raise GraphAgentFatalError(
            f"[F-v3-resource-reference-path-invalid] {relative_path!r} is not readable"
        )
    return candidate.read_text(encoding="utf-8")


def _excerpt(content: str, max_chars: int = 6000) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars]


__all__ = ["ReadReferenceArgs", "build_read_reference_tool"]
