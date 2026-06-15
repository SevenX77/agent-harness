"""GRAPH.md serializer for V0.3.0 YAML frontmatter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from graph_agent.core.loader import PhaseTokenInfo
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef, PhaseIOSchema

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


def serialize_graph_topology(
    *,
    name: str,
    description: str | None,
    io: PhaseIOSchema,
    phases: Sequence[GraphPhaseRef],
) -> str:
    """Serialize a canvas topology snapshot to canonical GRAPH.md Markdown.

    Unlike :func:`serialize_graph` (which only sees ``manifest.phases`` as a
    ``list[str]`` and therefore cannot carry edges), this takes the full phase
    refs so the body ``<phase depends_on=...>`` elements reflect the REAL graph.

    - ``depends_on``: comma-joined; a phase with no deps renders ``depends_on="input"``
      (the reserved entry sentinel — the loader requires a non-empty ``depends_on``).
    - ``output``: derived as the leaf phases (ids that appear in no other phase's
      ``depends_on``), satisfying the FROZEN rules "at least one output" and
      "an output phase has no downstream edges".
    """
    downstream = {dep for phase in phases for dep in phase.depends_on}
    lines = [
        "---",
        'schema_version: "v0.3.0"',
        f"name: {name}",
    ]
    if description:
        lines.append(f"description: {description}")
    lines.append("io:")
    lines.extend(_render_mapping(io.model_dump(mode="json"), indent=2))
    lines.append("phases:")
    for phase in phases:
        lines.append(f"  - {phase.id}")
    lines.append("---")
    for phase in phases:
        depends_on = ", ".join(phase.depends_on) if phase.depends_on else "input"
        output = " output" if phase.id not in downstream else ""
        lines.append(f'<phase depends_on="{depends_on}"{output}>{phase.id}</phase>')
    return "\n".join(lines) + "\n"


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


__all__ = ["GraphToken", "serialize_graph", "serialize_graph_topology"]
