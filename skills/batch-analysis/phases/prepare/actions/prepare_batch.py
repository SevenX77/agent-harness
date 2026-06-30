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


def prepare_batch(inputs) -> dict:
    """Prepare accumulated states and formatted texts for batch analysis."""
    acc_data = inputs.get("accumulated_context", {})

    acc = BatchAccumulator()
    if acc_data:
        if "known_characters" in acc_data:
            acc.known_characters = acc_data["known_characters"]
        if "known_props" in acc_data:
            acc.known_props = acc_data["known_props"]
        if "open_foreshadowing" in acc_data:
            acc.open_foreshadowing = acc_data["open_foreshadowing"]
        if "active_arcs" in acc_data:
            acc.active_arcs = acc_data["active_arcs"]
        if "character_latest_states" in acc_data:
            acc.character_latest_states = acc_data["character_latest_states"]
        if "time_tracker" in acc_data:
            acc.time_tracker = acc_data["time_tracker"]
        if "location_registry" in acc_data:
            acc.location_registry = acc_data["location_registry"]

    if hasattr(acc, "build_context_text"):
        accumulated_context_text = acc.build_context_text()
    else:
        lines = [
            f"Known Characters: {acc.known_characters}",
            f"Known Props: {acc.known_props}",
            f"Open Foreshadowing: {acc.open_foreshadowing}",
            f"Active Arcs: {acc.active_arcs}",
        ]
        accumulated_context_text = "\n".join(lines)

    events = inputs.get("batch_events", [])
    event_lines = []
    for event in events:
        event_id = event.get("event_id", "unknown")
        event_type = event.get("event_type", "unknown")
        content = event.get("content", "")
        event_lines.append(f"[{event_id}] ({event_type}): {content}")
    batch_events_text = "\n".join(event_lines)
    dimensions = inputs.get("dynamic_dimensions", [])
    if dimensions:
        dim_lines = [
            "Focus on the following narrative dimensions discovered in this batch:"
        ]
        dim_lines.extend(f"- {dimension}" for dimension in dimensions)
        dim_lines.append(
            "Pay special attention to these dimensions when analyzing character state changes."
        )
        dynamic_dimensions_hint = "\n".join(dim_lines)
    else:
        dynamic_dimensions_hint = ""

    chapter_range = inputs.get("chapter_range", [0, 0])
    batch_chapter_range = f"{chapter_range[0]}-{chapter_range[1]}"
    batch_event_count = len(events)

    return {
        "accumulated_context_text": accumulated_context_text,
        "batch_events_text": batch_events_text,
        "dynamic_dimensions_hint": dynamic_dimensions_hint,
        "batch_chapter_range": batch_chapter_range,
        "batch_event_count": batch_event_count,
        "accumulator": acc,
    }
