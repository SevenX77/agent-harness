import logging

logger = logging.getLogger(__name__)


class BatchAccumulator:
    def __init__(self):
        self.known_characters = {}
        self.known_props = {}
        self.open_foreshadowing = []
        self.active_arcs = []
        self.character_latest_states = {}
        self.time_tracker = {}
        self.location_registry = {}


def assemble_batch(inputs) -> dict:
    """Assemble all parallel analysis results and save accumulated state."""
    def _validate_batch_analysis(ctx: dict) -> tuple[bool, list[str]]:
        errors = []
        required_results = [
            "tension_results",
            "character_results",
            "prop_results",
            "arc_results",
            "foreshadowing_results",
            "spatiotemporal_results",
            "system_results",
        ]

        for key in required_results:
            if key not in ctx or not ctx[key]:
                errors.append(f"Layer 1: Missing or empty {key}")

        is_valid = len(errors) == 0
        return is_valid, errors

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

            merged_ev = {
                "event_id": ev_id,
                "event_type": ev.get("event_type", ""),
                "content": ev.get("content", ""),
                "tension": tension.get(ev_id, {}),
                "system_evolution": system.get(ev_id, {}),
                "character_changes": character.get(ev_id, {}),
                "prop_changes": prop.get(ev_id, {}),
                "emotional_arc": arc.get(ev_id, {}),
                "foreshadowing": foreshadowing.get(ev_id, {}),
                "spatiotemporal": spatiotemporal.get(ev_id, {}),
                "elements": elements,
            }
            batch_result.append(merged_ev)

    # 2. Update accumulator state
    acc = inputs.get("accumulator")
    if not acc:
        acc = BatchAccumulator()

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

    char_results = inputs.get("character_results", [])
    prop_results = inputs.get("prop_results", [])
    fore_results = inputs.get("foreshadowing_results", [])
    arc_results = inputs.get("arc_results", [])
    spatiotemporal_results = inputs.get("spatiotemporal_results", [])

    for r in char_results:
        char_id = r.get("character_id") or r.get("entity_id")
        if char_id:
            acc.known_characters[char_id] = {
                "name": r.get("name", ""),
                "current_state": r.get("current_state", r.get("state", "")),
            }
            acc.character_latest_states[char_id] = r.get(
                "current_state", r.get("state", "")
            )

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

    # 3. Save accumulated state
    updated_accumulated = {}
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
            updated_accumulated[attr] = getattr(acc, attr)

    # 4. Validate results quality
    is_valid, errors = _validate_batch_analysis(inputs)
    if not is_valid:
        raise ValueError(
            f"Batch analysis quality validation failed: {'; '.join(errors)}"
        )

    logger.info("Batch analysis results successfully assembled.")
    return {
        "batch_result": batch_result,
        "updated_accumulated": updated_accumulated,
    }
