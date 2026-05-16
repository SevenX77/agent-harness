from graph_agent.cognitive.context_facade import Context


def prepare_batch(context: Context) -> None:
    """Normalize batch inputs into text summaries consumed by SKILL phases."""

    batch_events = list(context.get("batch_events", []))
    accumulated = dict(context.get("accumulated_context", {}) or {})
    chapter_range = list(context.get("chapter_range", []))
    dynamic_dimensions = list(context.get("dynamic_dimensions", []))

    event_lines = []
    for index, event in enumerate(batch_events, start=1):
        if isinstance(event, dict):
            label = event.get("id") or event.get("event_id") or index
            summary = event.get("summary") or event.get("content") or str(event)
        else:
            label = index
            summary = str(event)
        event_lines.append(f"{label}. {summary}")

    latest_states = accumulated.get("character_latest_states", {})
    context.update(
        batch_events=batch_events,
        accumulated_context=accumulated,
        batch_events_text="\n".join(event_lines),
        batch_event_count=len(batch_events),
        batch_chapter_range="-".join(str(item) for item in chapter_range),
        dynamic_dimensions_hint=", ".join(str(item) for item in dynamic_dimensions),
        character_latest_states_text=str(latest_states),
    )
