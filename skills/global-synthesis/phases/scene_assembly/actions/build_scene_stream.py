from graph_agent.cognitive.context_facade import Context


def build_scene_stream(context: Context) -> None:
    """Build a unified event stream and coarse scenes from batch outputs."""

    batch_outputs = list(context.get("batch_outputs", []))
    events = []
    for batch in batch_outputs:
        if not isinstance(batch, dict):
            continue
        batch_result = batch.get("batch_result", batch)
        timeline = batch_result.get("event_timeline", batch_result.get("events", []))
        if isinstance(timeline, dict):
            timeline = timeline.get("events", [])
        if isinstance(timeline, list):
            events.extend(timeline)
    scenes = [
        {
            "scene_id": f"SCN-{index:03d}",
            "event_id": event.get("event_id", str(index)) if isinstance(event, dict) else str(index),
            "summary": event.get("summary", str(event)) if isinstance(event, dict) else str(event),
        }
        for index, event in enumerate(events, start=1)
    ]
    context.update(unified_event_stream=events, scenes=scenes)
