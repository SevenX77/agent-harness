from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)

CORRECTABLE_FIELDS = [
    "clothing",
    "makeup",
    "hygiene",
    "injuries",
    "key_relationships",
    "social_position",
    "normalized_location",
    "lighting_vibe",
]


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Scan and apply retroactive corrections from later anchors to earlier inferred fields."""
    batch_outputs = copy.deepcopy(state_slice.get("batch_outputs") or [])

    # 1. scan_anchor_points logic
    all_events = []
    for batch in batch_outputs:
        events = batch.get("events", [])
        all_events.extend(events)

    all_events.sort(
        key=lambda x: (x.get("chapter_number", 0), x.get("event_id", ""))
    )

    corrections = []
    for idx, ev in enumerate(all_events):
        is_inferred = ev.get("is_inferred", {})
        if not is_inferred:
            continue

        for field in CORRECTABLE_FIELDS:
            # Check if this field was inferred as true
            # Note: is_inferred can be dict[str, bool] or a list of field names. We handle both.
            inferred_flag = False
            if isinstance(is_inferred, dict):
                inferred_flag = is_inferred.get(field, False)
            elif isinstance(is_inferred, list):
                inferred_flag = field in is_inferred

            if not inferred_flag:
                continue

            current_val = ev.get(field, "")

            corrected_val = None
            anchor_event_id = None

            # Look for a later event with an explicit (non-inferred) value
            for later_ev in all_events[idx + 1 :]:
                later_inferred = later_ev.get("is_inferred", {})
                later_inferred_flag = False
                if isinstance(later_inferred, dict):
                    later_inferred_flag = later_inferred.get(field, False)
                elif isinstance(later_inferred, list):
                    later_inferred_flag = field in later_inferred

                if not later_inferred_flag:
                    corrected_val = later_ev.get(field)
                    anchor_event_id = later_ev.get("event_id")
                    break

            if corrected_val is not None and corrected_val != current_val:
                corrections.append(
                    {
                        "event_id": ev.get("event_id"),
                        "field": field,
                        "current_value": current_val,
                        "corrected_value": corrected_val,
                        "anchor_event_id": anchor_event_id,
                        "reason": f"Field {field} was inferred at {ev.get('event_id')}, but explicitly defined at {anchor_event_id}",
                    }
                )

    # 2. apply_corrections logic
    applied_count = 0
    for corr in corrections:
        event_id = corr.get("event_id")
        field = corr.get("field")
        new_val = corr.get("corrected_value")

        for batch in batch_outputs:
            events = batch.get("events", [])
            for ev in events:
                if ev.get("event_id") == event_id:
                    ev[field] = new_val
                    # Clear inference flag
                    is_inf = ev.get("is_inferred")
                    if isinstance(is_inf, dict) and field in is_inf:
                        ev["is_inferred"][field] = False
                    elif isinstance(is_inf, list) and field in is_inf:
                        ev["is_inferred"] = [x for x in is_inf if x != field]
                    applied_count += 1
                    break

    logger.info(
        f"Retroactive complete: found and applied {applied_count} corrections"
    )

    return {
        "retroactive_corrections": corrections,
        "batch_outputs": batch_outputs,
    }
