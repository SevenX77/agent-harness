from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def check_continuity(context: dict) -> str:
    warnings = []
    latest_states = context.get("character_latest_states", {})
    char_results = context.get("character_results", [])

    current_results_map = {r.get("character_id"): r for r in char_results}

    for char_id, prev_state in latest_states.items():
        if char_id not in current_results_map:
            continue

        current = current_results_map[char_id]
        current_appearance = current.get("appearance", current.get("physical_state", ""))
        prev_appearance = (
            prev_state.get("appearance", prev_state.get("physical_state", ""))
            if isinstance(prev_state, dict)
            else prev_state
        )

        if prev_appearance and current_appearance and prev_appearance != current_appearance:
            supporting_events = current.get("supporting_events", [])
            if not supporting_events:
                warnings.append(
                    {
                        "type": "appearance_mutation",
                        "entity_id": char_id,
                        "field": "appearance",
                        "expected": prev_appearance,
                        "actual": current_appearance,
                        "message": (
                            f"Character {char_id} appearance changed without event support: "
                            f"{prev_appearance} -> {current_appearance}"
                        ),
                    }
                )

        prev_status = (
            prev_state.get("status", prev_state.get("life_status", ""))
            if isinstance(prev_state, dict)
            else ""
        )
        current_status = current.get("status", current.get("life_status", ""))

        if prev_status == "dead" and current_status not in ["dead", "deceased", ""]:
            warnings.append(
                {
                    "type": "dead_character_appears",
                    "entity_id": char_id,
                    "field": "status",
                    "expected": "dead",
                    "actual": current_status,
                    "message": f"Dead character {char_id} appears as {current_status}",
                }
            )

    context["continuity_warnings"] = warnings
    return f"Found {len(warnings)} continuity issues"


def log_continuity_warning(
    entity_id: str, field: str, expected: str, actual: str, context: dict
) -> str:
    warnings = context.setdefault("continuity_warnings", [])

    warning = {
        "type": "manual_log",
        "entity_id": entity_id,
        "field": field,
        "expected": expected,
        "actual": actual,
        "message": f"{entity_id}.{field}: expected {expected}, got {actual}",
    }

    warnings.append(warning)
    return f"Logged continuity warning for {entity_id}"
