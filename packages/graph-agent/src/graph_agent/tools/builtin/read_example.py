from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.tools.builtin.read_reference import read_resource_file


def read_declared_example(
    *,
    root: Path,
    examples: Mapping[str, Any],
    example_id: Any,
    query: Any = "",
) -> str:
    del query
    if not isinstance(example_id, str) or not example_id:
        raise GraphAgentFatalError("[F-v3-tool-argument-invalid] example_id must be a string")
    spec = examples.get(example_id)
    if spec is None:
        raise GraphAgentFatalError(f"[F-v3-resource-example-not-found] {example_id!r}")
    return read_resource_file(
        root=root,
        relative_path=getattr(spec, "path", ""),
        error_code="[F-v3-resource-example-path-invalid]",
    )


__all__ = ["read_declared_example"]
