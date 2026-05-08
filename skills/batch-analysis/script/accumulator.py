from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.schemas import BatchAccumulator  # noqa: E402


def load_accumulated_state(context: dict) -> str:
    acc_data = context.get("accumulated_context", {})

    if not acc_data:
        context["accumulator"] = BatchAccumulator()
        return "Created new BatchAccumulator"

    acc = BatchAccumulator()

    if hasattr(acc, "known_characters") and "known_characters" in acc_data:
        acc.known_characters = acc_data["known_characters"]
    if hasattr(acc, "known_props") and "known_props" in acc_data:
        acc.known_props = acc_data["known_props"]
    if hasattr(acc, "open_foreshadowing") and "open_foreshadowing" in acc_data:
        acc.open_foreshadowing = acc_data["open_foreshadowing"]
    if hasattr(acc, "active_arcs") and "active_arcs" in acc_data:
        acc.active_arcs = acc_data["active_arcs"]
    if hasattr(acc, "character_latest_states") and "character_latest_states" in acc_data:
        acc.character_latest_states = acc_data["character_latest_states"]
    if hasattr(acc, "time_tracker") and "time_tracker" in acc_data:
        acc.time_tracker = acc_data["time_tracker"]
    if hasattr(acc, "location_registry") and "location_registry" in acc_data:
        acc.location_registry = acc_data["location_registry"]

    context["accumulator"] = acc
    return "Loaded accumulated state"


def build_batch_context_text(context: dict) -> str:
    acc = context.get("accumulator")
    if not acc:
        context["accumulated_context_text"] = ""
        return "No accumulator available"

    if hasattr(acc, "build_context_text"):
        text = acc.build_context_text()
    else:
        lines = []
        if hasattr(acc, "known_characters"):
            lines.append(f"Known Characters: {acc.known_characters}")
        if hasattr(acc, "known_props"):
            lines.append(f"Known Props: {acc.known_props}")
        if hasattr(acc, "open_foreshadowing"):
            lines.append(f"Open Foreshadowing: {acc.open_foreshadowing}")
        if hasattr(acc, "active_arcs"):
            lines.append(f"Active Arcs: {acc.active_arcs}")
        text = "\n".join(lines)

    context["accumulated_context_text"] = text
    return "Built context text"


def update_accumulator(context: dict) -> str:
    acc = context.get("accumulator")
    if not acc:
        acc = BatchAccumulator()
        context["accumulator"] = acc

    char_results = context.get("character_results", [])
    prop_results = context.get("prop_results", [])
    fore_results = context.get("foreshadowing_results", [])
    arc_results = context.get("arc_results", [])
    context.get("tension_results", [])
    spatiotemporal_results = context.get("spatiotemporal_results", [])

    if not hasattr(acc, "known_characters"):
        acc.known_characters = {}
    if not hasattr(acc, "known_props"):
        acc.known_props = {}
    if not hasattr(acc, "open_foreshadowing"):
        acc.open_foreshadowing = []
    if not hasattr(acc, "active_arcs"):
        acc.active_arcs = []
    if not hasattr(acc, "character_latest_states"):
        acc.character_latest_states = {}
    if not hasattr(acc, "time_tracker"):
        acc.time_tracker = {}
    if not hasattr(acc, "location_registry"):
        acc.location_registry = {}

    for r in char_results:
        char_id = r.get("character_id") or r.get("entity_id")
        if char_id:
            acc.known_characters[char_id] = {
                "name": r.get("name", ""),
                "current_state": r.get("current_state", r.get("state", "")),
            }
            acc.character_latest_states[char_id] = r.get("current_state", r.get("state", ""))

    for r in prop_results:
        prop_id = r.get("prop_id") or r.get("entity_id")
        if prop_id:
            acc.known_props[prop_id] = {
                "name": r.get("name", ""),
                "current_state": r.get("current_state", r.get("state", "")),
            }

    for r in fore_results:
        if r.get("is_resolved"):
            acc.open_foreshadowing = [
                f
                for f in acc.open_foreshadowing
                if f.get("foreshadowing_id") != r.get("foreshadowing_id")
            ]
        else:
            acc.open_foreshadowing.append(r)

    for r in arc_results:
        arc_id = r.get("arc_id")
        if arc_id and r.get("is_active", True):
            if arc_id not in [a.get("arc_id") for a in acc.active_arcs]:
                acc.active_arcs.append(r)

    for r in spatiotemporal_results:
        if r.get("location"):
            acc.location_registry[r.get("location")] = r.get(
                "normalized_location", r.get("location")
            )
        if r.get("timestamp"):
            acc.time_tracker[r.get("event_id", "")] = r.get("timestamp")

    return "Updated accumulator"


def save_accumulated_state(context: dict) -> str:
    acc = context.get("accumulator")
    if not acc:
        context["updated_accumulated"] = {}
        return "No accumulator to save"

    data = {}
    for attr in [
        "known_characters",
        "known_props",
        "open_foreshadowing",
        "active_arcs",
        "character_latest_states",
        "time_tracker",
        "location_registry",
    ]:
        if hasattr(acc, attr):
            data[attr] = getattr(acc, attr)

    context["updated_accumulated"] = data
    return "Saved accumulated state"
