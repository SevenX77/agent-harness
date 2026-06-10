from __future__ import annotations

import copy


def prepare_batches(inputs) -> dict:
    """Build paragraph lookup and normalize global timeline events into batches."""
    segmentation_result = inputs.get("segmentation_result") or []
    global_timeline = inputs.get("global_timeline") or {}
    batch_size = inputs.get("batch_size", 10)

    if not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")

    para_text_lookup = {}
    for chapter in segmentation_result:
        chapter_number = chapter.get("chapter_number")
        for paragraph in chapter.get("paragraphs", []) or []:
            paragraph_index = paragraph.get("index")
            if chapter_number is None or paragraph_index is None:
                continue
            para_text_lookup[f"{chapter_number}:{paragraph_index}"] = paragraph.get(
                "content", ""
            )

    normalized_events = []
    for event in global_timeline.get("events", []) or []:
        normalized_event = copy.deepcopy(event)
        chapter_number = normalized_event.get("chapter_number")
        paragraph_indices = normalized_event.get("paragraph_indices") or []
        content_parts = [
            para_text_lookup.get(f"{chapter_number}:{paragraph_index}", "")
            for paragraph_index in paragraph_indices
        ]
        normalized_event["event_type"] = normalized_event.get(
            "type", normalized_event.get("event_type", "")
        )
        normalized_event["content"] = "\n".join(
            part for part in content_parts if part
        )
        normalized_events.append(normalized_event)

    event_batches = []
    for start in range(0, len(normalized_events), batch_size):
        batch_events = normalized_events[start : start + batch_size]
        chapter_numbers = [
            event.get("chapter_number")
            for event in batch_events
            if isinstance(event.get("chapter_number"), int)
        ]
        if chapter_numbers:
            chapter_range = [min(chapter_numbers), max(chapter_numbers)]
        else:
            chapter_range = [0, 0]
        event_batches.append(
            {
                "batch_index": len(event_batches),
                "chapter_range": chapter_range,
                "events": batch_events,
            }
        )

    return {"event_batches": event_batches, "para_text_lookup": para_text_lookup}
