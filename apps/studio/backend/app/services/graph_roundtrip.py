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
    )


def execution_fingerprint(graph: dict[str, Any]) -> str:
    g = copy.deepcopy(graph)
    # Remove UI-only metadata from top-level
    g.pop("ui", None)
    g.pop("viewport", None)
    g.pop("selected_nodes", None)
    g.pop("editor_decorations", None)

    canonical = json.dumps(g, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
