from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.adapters.engine import GraphPhaseRef, PhaseIOSchema


def serialize_graph(manifest: Any, original_md: str) -> str:
    from app.core.adapters.engine import serialize_graph as sdk_serialize_graph

    return sdk_serialize_graph(manifest, original_md)


def serialize_graph_topology(
    *,
    name: str,
    description: str | None,
    io: PhaseIOSchema,
    phases: Sequence[GraphPhaseRef],
    original_md: str | None = None,
) -> str:
    """Serialize a canvas topology (phase ids + real depends_on) to GRAPH.md.

    Shared roundtrip boundary so Studio never imports the engine serializer
    module directly. Delegates to the engine's topology-aware serializer, which
    emits the real per-phase ``depends_on`` and leaf-derived ``output`` markers.
    """
    from app.core.adapters.engine import serialize_graph_topology as sdk_serialize_graph_topology

    return sdk_serialize_graph_topology(
        name=name,
        description=description,
        io=io,
        phases=phases,
        original_md=original_md,
    )


def execution_fingerprint(graph: dict[str, Any]) -> str:
    g = _without_ui_metadata(copy.deepcopy(graph))

    canonical = json.dumps(g, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _without_ui_metadata(value: Any) -> Any:
    ui_only_keys = {
        "ui",
        "metadata",
        "comments",
        "viewport",
        "selected_nodes",
        "editor_decorations",
        "position",
    }
    if isinstance(value, dict):
        return {
            key: _without_ui_metadata(child)
            for key, child in value.items()
            if key not in ui_only_keys
        }
    if isinstance(value, list):
        return [_without_ui_metadata(item) for item in value]
    return value
