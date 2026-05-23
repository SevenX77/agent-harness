"""V0.3.0 builtin read_example tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.manifest import ExampleSpec
from graph_agent.tools.builtin.read_reference import _read_skill_root_file


class ReadExampleArgs(BaseModel):
    example_id: str
    query: str = ""


def build_read_example_tool(
    *,
    skill_root: Path,
    examples: list[ExampleSpec],
) -> object:
    by_id = {item.id: item for item in examples}

    def read_example(example_id: str, query: str = "") -> str:
        spec = by_id.get(example_id)
        if spec is None:
            raise GraphAgentFatalError(f"[F-v3-resource-example-not-found] {example_id!r}")
        if spec.type == "inline":
            content = spec.content or ""
        else:
            if spec.path is None:
                raise GraphAgentFatalError(
                    f"[F-v3-resource-example-path-invalid] {example_id!r}"
                )
            content = _read_skill_root_file(skill_root, spec.path)
        query_line = f"\n\nQuery: {query}" if query else ""
        return f"# Example {spec.id} ({spec.type}){query_line}\n\n{content}"

    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=read_example,
        name="read_example",
        description="Read an example registered on the current Agent phase.",
        args_schema=ReadExampleArgs,
    )


__all__ = ["ReadExampleArgs", "build_read_example_tool"]
