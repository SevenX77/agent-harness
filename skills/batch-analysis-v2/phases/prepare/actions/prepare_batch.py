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
    "character_results": [],
}


def _normalized_accumulator_state(accumulated_context: dict) -> dict:
    state = copy.deepcopy(accumulated_context or {})
    for key, default_value in _ACCUMULATOR_DEFAULTS.items():
        if key not in state:
            state[key] = copy.deepcopy(default_value)
    return state


def _build_context_text(accumulator_state: dict) -> str:
    lines = []
    if accumulator_state.get("known_characters"):
        lines.append(f"Known Characters: {accumulator_state['known_characters']}")
    if accumulator_state.get("known_props"):
        lines.append(f"Known Props: {accumulator_state['known_props']}")
    if accumulator_state.get("open_foreshadowing"):
        lines.append(f"Open Foreshadowing: {accumulator_state['open_foreshadowing']}")
    if accumulator_state.get("active_arcs"):
        lines.append(f"Active Arcs: {accumulator_state['active_arcs']}")
    if accumulator_state.get("character_latest_states"):
        lines.append(
            f"Character Latest States: {accumulator_state['character_latest_states']}"
        )
    if accumulator_state.get("time_tracker"):
        lines.append(f"Time Tracker: {accumulator_state['time_tracker']}")
    if accumulator_state.get("location_registry"):
        lines.append(f"Location Registry: {accumulator_state['location_registry']}")
    return "\n".join(lines)


def _format_state_value(value) -> str:
    if isinstance(value, dict):
        parts = [
            f"{key}: {val}"
            for key, val in value.items()
            if val not in (None, "", [], {})
        ]
        return "; ".join(parts) if parts else "状态详情为空"
    if isinstance(value, list):
        return "; ".join(str(item) for item in value) if value else "状态详情为空"
    return str(value) if value not in (None, "") else "状态详情为空"


def _build_character_latest_states_text(accumulator_state: dict) -> str:
    states = accumulator_state.get("character_latest_states") or {}
    if not states:
        return "无前序角色最新状态。"

    lines = ["前序角色最新状态："]
    for character_id, state in sorted(states.items()):
        lines.append(f"- {character_id}: {_format_state_value(state)}")
    return "\n".join(lines)


def _build_batch_character_changes_text(accumulator_state: dict) -> str:
    character_results = (
        accumulator_state.get("character_results")
        or accumulator_state.get("character_changes")
        or []
    )
    if not character_results:
        return "无本批次角色变化记录。"

    lines = ["本批次角色变化："]
    for result in character_results:
        if not isinstance(result, dict):
            lines.append(f"- {result}")
            continue

        event_id = result.get("event_id", "unknown")
        character_id = (
            result.get("character_id")
            or result.get("entity_id")
            or result.get("name")
            or "unknown"
        )
        current_state = result.get("current_state") or result.get("state") or ""
        changes = result.get("changes") or []
        if isinstance(changes, list):
            changes_text = "; ".join(str(item) for item in changes)
        else:
            changes_text = str(changes)

        detail_parts = []
        if current_state:
            detail_parts.append(f"current_state: {current_state}")
        if changes_text:
            detail_parts.append(f"changes: {changes_text}")
        details = "; ".join(detail_parts) if detail_parts else _format_state_value(result)
        lines.append(f"- [{event_id}] {character_id}: {details}")
    return "\n".join(lines)



def _lookup_paragraph_text(para_text_lookup: dict, paragraph_index) -> str:
    paragraph = para_text_lookup.get(paragraph_index)
    if paragraph is None:
        paragraph = para_text_lookup.get(str(paragraph_index))
    if isinstance(paragraph, dict):
        return (
            paragraph.get("text")
            or paragraph.get("content")
            or paragraph.get("paragraph_text")
            or ""
        )
    return str(paragraph) if paragraph is not None else ""


def _event_content(ev: dict, para_text_lookup: dict) -> str:
    content = ev.get("content") or ev.get("text") or ""
    if content:
        return str(content)

    paragraph_indices = ev.get("paragraph_indices") or ev.get("paragraphs") or []
    paragraph_texts = [
        _lookup_paragraph_text(para_text_lookup, paragraph_index)
        for paragraph_index in paragraph_indices
    ]
    paragraph_texts = [text for text in paragraph_texts if text]
    if paragraph_texts:
        return " ".join(paragraph_texts)

    return str(ev.get("summary") or "")


def prepare_batch(inputs) -> dict:
    """Prepare accumulated states and format texts for batch analysis."""
    accumulator_state = _normalized_accumulator_state(
        inputs.get("accumulated_context", {})
    )
    accumulated_context_text = _build_context_text(accumulator_state)
    character_latest_states_text = _build_character_latest_states_text(
        accumulator_state
    )
    batch_character_changes_text = _build_batch_character_changes_text(
        accumulator_state
    )

    events = inputs.get("batch_events", [])
    para_text_lookup = inputs.get("para_text_lookup", {})
    event_lines = []
    for ev in events:
        ev_id = ev.get("event_id", "unknown")
        ev_type = ev.get("event_type", "unknown")
        content = _event_content(ev, para_text_lookup)
        event_lines.append(f"[{ev_id}] ({ev_type}): {content}")

    batch_events_text = "\n".join(event_lines)

    dimensions = inputs.get("dynamic_dimensions", [])
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

    chapter_range = inputs.get("chapter_range", [0, 0])
    batch_chapter_range = f"{chapter_range[0]}-{chapter_range[1]}"

    batch_event_count = len(events)

    return {
        "accumulated_context_text": accumulated_context_text,
        "batch_events_text": batch_events_text,
        "dynamic_dimensions_hint": dynamic_dimensions_hint,
        "batch_chapter_range": batch_chapter_range,
        "batch_event_count": batch_event_count,
        "accumulator_state": accumulator_state,
        "character_latest_states_text": character_latest_states_text,
        "batch_character_changes_text": batch_character_changes_text,
    }
