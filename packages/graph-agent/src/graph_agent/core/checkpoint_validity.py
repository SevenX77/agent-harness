"""Node-scoped checkpoint validity and resume selection helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def checkpoint_validity_by_phase(
    compiled: Any,
    *,
    dirty_phase_ids: Iterable[str],
) -> dict[str, bool]:
    """Return per-phase checkpoint validity after node-local dirty changes."""
    dirty = {phase for phase in dirty_phase_ids if phase}
    order = _phase_order(compiled)
    downstream = _downstream_map(_phase_dependencies(compiled))
    invalid = set(dirty)
    queue = list(dirty)
    while queue:
        phase = queue.pop(0)
        for child in downstream.get(phase, set()):
            if child in invalid:
                continue
            invalid.add(child)
            queue.append(child)
    return {phase: phase not in invalid for phase in order}


def checkpoint_id_before_phase(
    checkpointer: Any,
    compiled: Any,
    *,
    run_id: str,
    checkpoint_ns: str,
    phase_id: str,
) -> str:
    """Select the latest checkpoint that is ready to execute ``phase_id``."""
    order = _phase_order(compiled)
    if phase_id not in order:
        raise ValueError(f"Unknown phase {phase_id!r}; expected one of: {', '.join(order)}")

    output_keys = _phase_output_keys(compiled)
    dependencies = _phase_dependencies(compiled)
    required_outputs = set()
    for upstream in _ancestor_phases(phase_id, dependencies):
        required_outputs.update(output_keys.get(upstream, set()))
    forbidden_outputs = output_keys.get(phase_id, set())

    search_config = {"configurable": {"thread_id": run_id, "checkpoint_ns": checkpoint_ns}}
    for checkpoint in checkpointer.list(search_config):
        data = _checkpoint_data(checkpoint)
        if not required_outputs.issubset(data.keys()):
            continue
        if forbidden_outputs.intersection(data.keys()):
            continue
        return str(checkpoint.checkpoint["id"])

    raise ValueError(
        f"No checkpoint before phase {phase_id!r} found in namespace {checkpoint_ns!r} "
        f"for run_id {run_id!r}"
    )


def _phase_order(compiled: Any) -> list[str]:
    topology = getattr(compiled, "raw", {}).get("graph_topology", {})
    order = topology.get("order")
    if isinstance(order, list) and all(isinstance(item, str) for item in order):
        return list(order)
    manifest = getattr(compiled, "manifest", None)
    phases = getattr(manifest, "phases", None)
    if isinstance(phases, list):
        return [phase for phase in phases if isinstance(phase, str)]
    return [str(node.phase_name) for node in getattr(compiled, "nodes", [])]


def _phase_dependencies(compiled: Any) -> dict[str, list[str]]:
    topology = getattr(compiled, "raw", {}).get("graph_topology", {})
    phases = topology.get("phases")
    dependencies: dict[str, list[str]] = {}
    if isinstance(phases, list):
        for row in phases:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            raw_deps = row.get("depends_on")
            if isinstance(name, str) and isinstance(raw_deps, list):
                dependencies[name] = [dep for dep in raw_deps if isinstance(dep, str)]
    for phase in _phase_order(compiled):
        dependencies.setdefault(phase, [])
    return dependencies


def _phase_output_keys(compiled: Any) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for node in getattr(compiled, "nodes", []):
        io = getattr(node, "frontmatter", {}).get("io") or {}
        outputs = io.get("outputs") or {}
        properties = outputs.get("properties") or {}
        if isinstance(properties, dict):
            keys[str(node.phase_name)] = {
                key for key in properties.keys() if isinstance(key, str)
            }
    return keys


def _downstream_map(dependencies: dict[str, list[str]]) -> dict[str, set[str]]:
    downstream: dict[str, set[str]] = {phase: set() for phase in dependencies}
    for phase, deps in dependencies.items():
        for dep in deps:
            if dep == "input":
                continue
            downstream.setdefault(dep, set()).add(phase)
    return downstream


def _ancestor_phases(phase_id: str, dependencies: dict[str, list[str]]) -> set[str]:
    ancestors: set[str] = set()
    queue = [dep for dep in dependencies.get(phase_id, []) if dep != "input"]
    while queue:
        dep = queue.pop(0)
        if dep in ancestors:
            continue
        ancestors.add(dep)
        queue.extend(item for item in dependencies.get(dep, []) if item != "input")
    return ancestors


def _checkpoint_data(checkpoint: Any) -> dict[str, Any]:
    values = checkpoint.checkpoint.get("channel_values", {})
    data = values.get("data")
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    if isinstance(data, dict):
        return dict(data)
    return {}


__all__ = ["checkpoint_id_before_phase", "checkpoint_validity_by_phase"]
