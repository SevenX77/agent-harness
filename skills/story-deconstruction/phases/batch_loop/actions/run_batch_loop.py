import logging

logger = logging.getLogger(__name__)


def run_batch_loop(inputs) -> dict:
    """Group flattened events into deterministic batches without nested skill calls."""
    all_events = inputs.get("all_events", [])

    flat_events = []
    for ch in all_events:
        ch_num = ch.get("chapter_number")
        for event in ch.get("events", []):
            flat_events.append({
                **event,
                "chapter_number": ch_num,
            })

    batch_size = 10
    total_batches = (len(flat_events) + batch_size - 1) // batch_size
    all_batch_results = []
    accumulated_context = {}

    for batch_index in range(total_batches):
        start_idx = batch_index * batch_size
        end_idx = start_idx + batch_size
        batch_events = flat_events[start_idx:end_idx]

        batch_chapters = sorted(set(e.get("chapter_number") for e in batch_events))
        if batch_events:
            if batch_chapters[0] == batch_chapters[-1]:
                chapter_range = str(batch_chapters[0])
            else:
                chapter_range = f"{batch_chapters[0]}-{batch_chapters[-1]}"
        else:
            chapter_range = "none"

        logger.info(f"Running batch analysis for Batch {batch_index + 1}: chapters {chapter_range}")

        all_batch_results.append({
            "batch_index": batch_index + 1,
            "chapter_range": chapter_range,
            "result": batch_events,
        })

    logger.info(f"Batch analysis completed: {len(all_batch_results)} batches")
    return {
        "batch_outputs": all_batch_results,
        "accumulated_context": accumulated_context,
        "entity_registry": accumulated_inputs.get("entity_registry", {}),
    }
