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


def prepare_batch(context) -> dict:
    """Prepare accumulated states and format texts for batch analysis."""
    acc_data = context.get("accumulated_context", {})

    # 1. Load accumulated state
    if not acc_data:
        acc = BatchAccumulator()
    else:
        acc = BatchAccumulator()
        if hasattr(acc, "known_characters") and "known_characters" in acc_data:
            acc.known_characters = acc_data["known_characters"]
        if hasattr(acc, "known_props") and "known_props" in acc_data:
            acc.known_props = acc_data["known_props"]
        if hasattr(acc, "open_foreshadowing") and "open_foreshadowing" in acc_data:
            acc.open_foreshadowing = acc_data["open_foreshadowing"]
        if hasattr(acc, "active_arcs") and "active_arcs" in acc_data:
            acc.active_arcs = acc_data["active_arcs"]
        if (
            hasattr(acc, "character_latest_states")
            and "character_latest_states" in acc_data
        ):
            acc.character_latest_states = acc_data["character_latest_states"]
        if hasattr(acc, "time_tracker") and "time_tracker" in acc_data:
            acc.time_tracker = acc_data["time_tracker"]
        if hasattr(acc, "location_registry") and "location_registry" in acc_data:
            acc.location_registry = acc_data["location_registry"]

    context["accumulator"] = acc

    # 2. Build batch context text
    if hasattr(acc, "build_context_text"):
        accumulated_context_text = acc.build_context_text()
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
        accumulated_context_text = "\n".join(lines)

    context["accumulated_context_text"] = accumulated_context_text

    # 3. Format batch events
    events = context.get("batch_events", [])
    event_lines = []
    for ev in events:
        ev_id = ev.get("event_id", "unknown")
        ev_type = ev.get("event_type", "unknown")
        content = ev.get("content", "")
        event_lines.append(f"[{ev_id}] ({ev_type}): {content}")

    batch_events_text = "\n".join(event_lines)
    context["batch_events_text"] = batch_events_text

    # 4. Format dynamic dimensions hint
    dimensions = context.get("dynamic_dimensions", [])
    if not dimensions:
        dynamic_dimensions_hint = ""
    else:
        dim_lines = [
            "以下是本批次需要重点追踪的叙事维度（由 Phase 3 自动发现）："
        ]
        for dim in dimensions:
            dim_lines.append(f"- {dim}")
        dim_lines.append("在分析角色状态变化时，请特别关注上述维度的变化。")
        dynamic_dimensions_hint = "\n".join(dim_lines)

    context["dynamic_dimensions_hint"] = dynamic_dimensions_hint

    # 5. Format chapter range
    chapter_range = context.get("chapter_range", [0, 0])
    batch_chapter_range = f"{chapter_range[0]}-{chapter_range[1]}"
    context["batch_chapter_range"] = batch_chapter_range

    batch_event_count = len(events)
    context["batch_event_count"] = batch_event_count

    return {
        "accumulated_context_text": accumulated_context_text,
        "batch_events_text": batch_events_text,
        "dynamic_dimensions_hint": dynamic_dimensions_hint,
        "batch_chapter_range": batch_chapter_range,
        "batch_event_count": batch_event_count,
    }
