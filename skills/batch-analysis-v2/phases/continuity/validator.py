from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Perform automated continuity checks and combine with Agent manually identified warnings."""
    # 1. Run automated checks (corresponds to script/continuity.py check_continuity)
    auto_warnings = []
    accumulator_state = state_slice.get("accumulator_state") or {}
    latest_states = accumulator_state.get("character_latest_states") or {}
    char_results = state_slice.get("character_results") or []

    current_results_map = {r.get("character_id"): r for r in char_results}

    for char_id, prev_state in latest_states.items():
        if char_id not in current_results_map:
            continue

        current = current_results_map[char_id]
        current_appearance = current.get(
            "appearance", current.get("physical_state", "")
        )
        prev_appearance = (
            prev_state.get("appearance", prev_state.get("physical_state", ""))
            if isinstance(prev_state, dict)
            else prev_state
        )

        if (
            prev_appearance
            and current_appearance
            and prev_appearance != current_appearance
        ):
            # Check for event support (supporting_events)
            supporting_events = current.get("supporting_events", [])
            if not supporting_events:
                auto_warnings.append(
                    {
                        "type": "appearance_mutation",
                        "entity_id": char_id,
                        "field": "appearance",
                        "expected": prev_appearance,
                        "actual": current_appearance,
                        "message": f"Character {char_id} appearance changed without event support: {prev_appearance} -> {current_appearance}",
                    }
                )

        prev_status = (
            prev_state.get("status", prev_state.get("life_status", ""))
            if isinstance(prev_state, dict)
            else ""
        )
        current_status = current.get("status", current.get("life_status", ""))

        if prev_status == "dead" and current_status not in [
            "dead",
            "deceased",
            "",
        ]:
            auto_warnings.append(
                {
                    "type": "dead_character_appears",
                    "entity_id": char_id,
                    "field": "status",
                    "expected": "dead",
                    "actual": current_status,
                    "message": f"Dead character {char_id} appears as {current_status}",
                }
            )

    # 2. Combine with Agent manual warnings
    agent_warnings = output.get("continuity_warnings") or []
    combined = list(auto_warnings)

    # Deduplicate manual vs auto
    seen_keys = set()
    for w in combined:
        key = (w.get("entity_id"), w.get("field"), w.get("actual"))
        seen_keys.add(key)

    for aw in agent_warnings:
        entity_id = aw.get("entity_id") or ""
        field = aw.get("field") or ""
        actual = aw.get("actual") or ""
        key = (entity_id, field, actual)

        if key not in seen_keys:
            warning = {
                "type": aw.get("type", "manual_log"),
                "entity_id": entity_id,
                "field": field,
                "expected": aw.get("expected") or "",
                "actual": actual,
                "message": aw.get("message")
                or f"{entity_id}.{field}: expected {aw.get('expected')}, got {actual}",
            }
            combined.append(warning)
            seen_keys.add(key)

    logger.info(
        f"Continuity validator finished: found {len(auto_warnings)} auto, merged to {len(combined)} total warnings"
    )

    return {"continuity_warnings": combined}
