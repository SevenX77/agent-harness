"""Per-phase io supply/demand projection for the Canvas data-gap view.

n2-canvas#10 (data-gap-viz): the engine's ``CompiledSkill`` already carries each
phase's ``io.inputs`` / ``io.outputs`` field schema on the per-node frontmatter
(the same ``frontmatter['io']`` the engine reads in ``runner._node_output_fields``).
This module projects that already-compiled data into a structured supply/demand
map the Canvas frontend can render as design-time data-gap markers, WITHOUT any
engine edit -- it only reads ``compiled.nodes``.

The projection answers, for every downstream phase input field: which upstream
phase (honoring ``depends_on`` order) produces a matching output field. A field
with no upstream producer and no graph-level input is a *data gap*.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.adapters.engine import CompiledSkill

logger = logging.getLogger(__name__)

# One entry per downstream input field: where (if anywhere) it is supplied from.
FieldSupply = dict[str, object]
# Per-phase io projection: {"inputs": {field: schema}, "outputs": {field: schema}}.
PhaseIoFields = dict[str, dict[str, object]]


def _io_block(frontmatter: object) -> dict[str, object]:
    """Read the ``io`` block off a compiled phase node's frontmatter."""
    if not isinstance(frontmatter, dict):
        return {}
    io = frontmatter.get("io")
    return io if isinstance(io, dict) else {}


def _field_properties(io_block: dict[str, object], direction: str) -> dict[str, object]:
    """Extract ``io.<direction>.properties`` field schema as a plain dict."""
    section = io_block.get(direction)
    if not isinstance(section, dict):
        return {}
    properties = section.get("properties")
    if not isinstance(properties, dict):
        return {}
    return {str(name): schema for name, schema in properties.items()}


def _phase_io_fields(node: object) -> PhaseIoFields:
    """Project one compiled phase node's input/output field schema."""
    io_block = _io_block(getattr(node, "frontmatter", {}))
    return {
        "inputs": _field_properties(io_block, "inputs"),
        "outputs": _field_properties(io_block, "outputs"),
    }


def _graph_input_fields(compiled: CompiledSkill) -> set[str]:
    """Graph-level ``io.inputs`` field names (the run's external inputs)."""
    raw = getattr(compiled, "raw", {})
    if not isinstance(raw, dict):
        return set()
    io_block = raw.get("io")
    if not isinstance(io_block, dict):
        return set()
    return set(_field_properties(io_block, "inputs"))


def build_phase_io_index(compiled: CompiledSkill) -> dict[str, PhaseIoFields]:
    """Map each phase name to its projected input/output field schema."""
    index: dict[str, PhaseIoFields] = {}
    for node in getattr(compiled, "nodes", []) or []:
        phase_name = getattr(node, "phase_name", None)
        if not isinstance(phase_name, str) or not phase_name:
            continue
        index[phase_name] = _phase_io_fields(node)
    logger.debug("canvas_data_gap built phase io index for %d phases", len(index))
    return index


def compute_field_supply(
    *,
    phase_name: str,
    depends_on: list[str],
    phase_io_index: dict[str, PhaseIoFields],
    graph_input_fields: set[str],
) -> list[FieldSupply]:
    """For each input field of ``phase_name``, resolve where it is supplied from.

    Supply resolution order (first match wins):
      1. an upstream dependency phase whose ``io.outputs`` declares the field;
      2. the graph-level ``io.inputs`` (external run input).
    A field matched by neither is flagged ``supplied=False`` -- a data gap the
    Canvas renders as a missing-input marker on the downstream node.
    """
    own_inputs = phase_io_index.get(phase_name, {}).get("inputs", {})
    supply: list[FieldSupply] = []
    for field_name in own_inputs:
        producer = _resolve_producer(field_name, depends_on, phase_io_index)
        if producer is not None:
            supply.append(
                {
                    "field": field_name,
                    "supplied": True,
                    "source": "phase",
                    "producer_phase": producer,
                }
            )
            continue
        if field_name in graph_input_fields:
            supply.append(
                {
                    "field": field_name,
                    "supplied": True,
                    "source": "graph_input",
                    "producer_phase": None,
                }
            )
            continue
        supply.append(
            {
                "field": field_name,
                "supplied": False,
                "source": "none",
                "producer_phase": None,
            }
        )
    return supply


def _resolve_producer(
    field_name: str,
    depends_on: list[str],
    phase_io_index: dict[str, PhaseIoFields],
) -> str | None:
    """Return the last declared upstream dependency that outputs ``field_name``."""
    producer: str | None = None
    for upstream in depends_on:
        outputs = phase_io_index.get(upstream, {}).get("outputs", {})
        if field_name in outputs:
            producer = upstream
    return producer
