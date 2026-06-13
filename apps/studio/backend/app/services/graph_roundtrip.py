from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def serialize_graph(manifest: Any, original_md: str) -> str:
    from app.core.adapters.engine import serialize_graph as sdk_serialize_graph

    return sdk_serialize_graph(manifest, original_md)


def execution_fingerprint(graph: dict[str, Any]) -> str:
    g = copy.deepcopy(graph)
    # Remove UI-only metadata from top-level
    g.pop("ui", None)
    g.pop("viewport", None)
    g.pop("selected_nodes", None)
    g.pop("editor_decorations", None)

    canonical = json.dumps(g, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
