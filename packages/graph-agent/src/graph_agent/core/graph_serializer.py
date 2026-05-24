"""Canonical GRAPH.md serializer for V0.3.0 graph manifests."""

from __future__ import annotations

import json

from graph_agent.core.manifest import GraphManifest


def serialize_graph(manifest: GraphManifest, original_md: str | None = None) -> str:
    """Serialize a V0.3.0 GraphManifest as frontmatter-only GRAPH.md."""

    del original_md
    lines = [
        "---",
        'schema_version: "0.3.0"',
        f"name: {manifest.name}",
    ]
    if manifest.description:
        lines.append(f"description: {manifest.description}")
    lines.append("io:")
    lines.append(f"  inputs: {json.dumps(manifest.io.inputs, ensure_ascii=False)}")
    lines.append(f"  outputs: {json.dumps(manifest.io.outputs, ensure_ascii=False)}")
    lines.append("phases:")
    for phase in manifest.phases:
        lines.append(f"  - id: {phase.id}")
        lines.append(f"    src: {phase.src}")
        lines.append(
            f"    depends_on: {json.dumps(phase.depends_on, ensure_ascii=False)}"
        )
    lines.append("---")
    return "\n".join(lines) + "\n"


__all__ = ["serialize_graph"]
