from __future__ import annotations

import copy


def prepare_batches(inputs) -> dict:
    """Normalize global timeline events into fixed-size batches.

    Each event's ``content`` is filled with the original paragraph prose
    (looked up from ``segmentation_result`` by chapter_number + paragraph
    indices) so downstream multi-dimensional analysis reads source text, not
    only the short event summary. ``para_text_lookup`` (``"<chapter>:<index>"
    -> content``) is also emitted for compatibility.
    """
    global_timeline = inputs.get("global_timeline") or {}
    segmentation_result = inputs.get("segmentation_result") or []
    batch_size = 10

    if not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")

    # Build paragraph-text index from segmentation: (chapter, index) -> content.
    para_index: dict[tuple, str] = {}
    para_text_lookup: dict[str, str] = {}
    for chapter_seg in segmentation_result:
        if not isinstance(chapter_seg, dict):
            continue
        chapter_number = chapter_seg.get("chapter_number")
        for para in chapter_seg.get("paragraphs", []) or []:
            if not isinstance(para, dict):
                continue
            para_idx = para.get("index")
            content = str(para.get("content") or "")
            para_index[(chapter_number, para_idx)] = content
            para_text_lookup[f"{chapter_number}:{para_idx}"] = content

    normalized_events = []
    for event in global_timeline.get("events", []) or []:
        normalized_event = copy.deepcopy(event)
        chapter_number = normalized_event.get("chapter_number")
        paragraph_indices = normalized_event.get("paragraph_indices") or []
        normalized_event["event_type"] = normalized_event.get(
            "type", normalized_event.get("event_type", "")
        )
        # Prefer original paragraph prose; fall back to existing content/summary.
        existing = normalized_event.get("content") or normalized_event.get("text")
        if existing:
            normalized_event["content"] = str(existing)
        else:
            paras = [
                para_index.get((chapter_number, pi), "")
                for pi in paragraph_indices
            ]
            paras = [p for p in paras if p]
            normalized_event["content"] = (
                " ".join(paras) if paras else str(normalized_event.get("summary") or "")
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
