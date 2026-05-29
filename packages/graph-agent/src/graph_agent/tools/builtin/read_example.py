from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload
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
        detail = "example_id must be a string"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-tool-argument-invalid]", detail),
        )
    spec = examples.get(example_id)
    if spec is None:
        detail = f"{example_id!r}"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-resource-example-not-found]", detail),
        )
    return read_resource_file(
        root=root,
        relative_path=getattr(spec, "path", ""),
        code="[F-v3-resource-example-path-invalid]",
    )


__all__ = ["read_declared_example"]
