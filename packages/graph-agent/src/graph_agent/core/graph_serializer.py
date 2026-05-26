"""GRAPH.md serializer for V0.3.0 YAML frontmatter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from graph_agent.core.loader import PhaseTokenInfo
from graph_agent.core.manifest import GraphManifest

TokenKind = Literal["frontmatter", "comment", "phase", "whitespace", "text"]


@dataclass(frozen=True)
class GraphToken:
    kind: TokenKind
    start: int
    end: int
    text: str
    phase_id: str | None = None
    phase_info: PhaseTokenInfo | None = None


def serialize_graph(manifest: GraphManifest, original_md: str | None = None) -> str:
    """Serialize a GraphManifest back to canonical GRAPH.md Markdown."""

    del original_md
    return _render_fresh_graph(manifest)


def _render_fresh_graph(manifest: GraphManifest) -> str:
    lines = [
        "---",
        'schema_version: "v0.3.0"',
        f"name: {manifest.name}",
    ]
    if manifest.description:
        lines.append(f"description: {manifest.description}")
    lines.append("io:")
    lines.extend(_render_mapping(manifest.io.model_dump(mode="json"), indent=2))
    lines.append("phases:")
    for phase in manifest.phases:
        lines.append(f"  - {phase}")
    lines.append("---")
    for index, phase in enumerate(manifest.phases):
        depends_on = "input" if index == 0 else manifest.phases[index - 1]
        output = " output" if index == len(manifest.phases) - 1 else ""
        lines.append(f'<phase depends_on="{depends_on}"{output}>{phase}</phase>')
    return "\n".join(lines) + "\n"


def _render_mapping(value: object, *, indent: int) -> list[str]:
    prefix = " " * indent
    if not isinstance(value, dict):
        return [prefix + _scalar(value)]
    lines: list[str] = []
    for key, item in value.items():
        if isinstance(item, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_render_mapping(item, indent=indent + 2))
        elif isinstance(item, list):
            lines.append(f"{prefix}{key}:")
            for entry in item:
                lines.append(f"{prefix}  - {_scalar(entry)}")
        else:
            lines.append(f"{prefix}{key}: {_scalar(item)}")
    return lines


def _scalar(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        if value == "" or any(ch in value for ch in ":#[]{}"):
            return repr(value)
        return value
    return str(value)


__all__ = ["GraphToken", "serialize_graph"]
