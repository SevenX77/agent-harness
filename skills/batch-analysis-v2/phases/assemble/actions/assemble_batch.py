import copy
import logging

logger = logging.getLogger(__name__)


_ACCUMULATOR_DEFAULTS = {
    "known_characters": {},
    "known_props": {},
    "open_foreshadowing": [],
    "active_arcs": [],
    "character_latest_states": {},
    "time_tracker": {},
    "location_registry": {},
    "entity_registry": {},
    "entity_aliases": {},
}


def _normalized_accumulator_state(accumulator_state: dict) -> dict:
    state = copy.deepcopy(accumulator_state or {})
    for key, default_value in _ACCUMULATOR_DEFAULTS.items():
        if key not in state:
            state[key] = copy.deepcopy(default_value)
    return state


def assemble_batch(inputs) -> dict:
    """Assemble all parallel analysis results and save accumulated state."""
    events = inputs.get("batch_events", [])
    if not events:
        batch_result = []
    else:
        tension = {
            r.get("event_id", ""): r for r in inputs.get("tension_results", [])
        }
        system = {
            r.get("event_id", ""): r for r in inputs.get("system_results", [])
        }
        character = {
            r.get("event_id", ""): r
            for r in inputs.get("character_results", [])
        }
        prop = {r.get("event_id", ""): r for r in inputs.get("prop_results", [])}
        arc = {r.get("event_id", ""): r for r in inputs.get("arc_results", [])}
        foreshadowing = {
            r.get("event_id", ""): r
            for r in inputs.get("foreshadowing_results", [])
        }
        spatiotemporal = {
            r.get("event_id", ""): r
            for r in inputs.get("spatiotemporal_results", [])
        }

        batch_result = []
        for ev in events:
            ev_id = ev.get("event_id", "")
            elements = {
                "character_evolution": character.get(ev_id, {}).get(
                    "changes", []
                ),
                "prop_evolution": prop.get(ev_id, {}).get("changes", []),
                "emotion_curve": arc.get(ev_id, {}).get("curve", []),
            }

            merged_ev = copy.deepcopy(ev)
            merged_ev.update(
                {
                    "tension": tension.get(ev_id, {}),
                    "system_evolution": system.get(ev_id, {}),
                    "character_changes": character.get(ev_id, {}),
                    "prop_changes": prop.get(ev_id, {}),
                    "emotional_arc": arc.get(ev_id, {}),
                    "foreshadowing": foreshadowing.get(ev_id, {}),
                    "spatiotemporal": spatiotemporal.get(ev_id, {}),
                    "elements": elements,
                }
            )
            batch_result.append(merged_ev)

    updated_accumulated = _normalized_accumulator_state(
        inputs.get("accumulator_state", {})
    )
    if inputs.get("entity_registry") is not None:
        updated_accumulated["entity_registry"] = copy.deepcopy(inputs["entity_registry"])
    if inputs.get("entity_aliases") is not None:
        updated_accumulated["entity_aliases"] = copy.deepcopy(inputs["entity_aliases"])

    char_results = inputs.get("character_results", [])
    prop_results = inputs.get("prop_results", [])
    fore_results = inputs.get("foreshadowing_results", [])
    arc_results = inputs.get("arc_results", [])
    spatiotemporal_results = inputs.get("spatiotemporal_results", [])

    for r in char_results:
        char_id = r.get("character_id") or r.get("entity_id")
        if char_id:
            updated_accumulated["known_characters"][char_id] = {
                "name": r.get("name", ""),
                "current_state": r.get("current_state", r.get("state", "")),
            }
            updated_accumulated["character_latest_states"][char_id] = r.get(
                "current_state", r.get("state", "")
            )

    for r in prop_results:
        prop_id = r.get("prop_id") or r.get("entity_id")
        if prop_id:
            updated_accumulated["known_props"][prop_id] = {
                "name": r.get("name", ""),
                "current_state": r.get("current_state", r.get("state", "")),
            }

    for r in fore_results:
        if r.get("is_resolved"):
            updated_accumulated["open_foreshadowing"] = [
                f
                for f in updated_accumulated["open_foreshadowing"]
                if f.get("foreshadowing_id") != r.get("foreshadowing_id")
            ]
        else:
            updated_accumulated["open_foreshadowing"].append(r)

    for r in arc_results:
        arc_id = r.get("arc_id")
        if arc_id and r.get("is_active", True):
            active_arc_ids = [
                a.get("arc_id") for a in updated_accumulated["active_arcs"]
            ]
            if arc_id not in active_arc_ids:
                updated_accumulated["active_arcs"].append(r)

    for r in spatiotemporal_results:
        if r.get("location"):
            updated_accumulated["location_registry"][r.get("location")] = r.get(
                "normalized_location", r.get("location")
            )
        if r.get("timestamp"):
            updated_accumulated["time_tracker"][r.get("event_id", "")] = r.get(
                "timestamp"
            )

    logger.info("Batch analysis results successfully assembled.")
    return {
        "batch_result": batch_result,
        "updated_accumulated": updated_accumulated,
    }
