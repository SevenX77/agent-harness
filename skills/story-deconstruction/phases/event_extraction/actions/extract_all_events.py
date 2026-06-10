import logging

logger = logging.getLogger(__name__)


def extract_all_events(context) -> dict:
    """Collect event entries from segmentation records without nested skill calls."""
    all_segmentations = context.get("all_segmentations", [])
    all_events = []

    for seg_data in all_segmentations:
        chapter_number = seg_data.get("chapter_number")
        segmentation = seg_data.get("segmentation", {})
        chapter_events = segmentation.get("events")
        if not isinstance(chapter_events, list):
            chapter_events = []

        all_events.append({
            "chapter_number": chapter_number,
            "events": chapter_events,
        })

    total_events = sum(len(ch.get("events", [])) for ch in all_events)
    total_chapters = len(all_events)

    logger.info(f"Extracted {total_events} events from {total_chapters} chapters")
    return {
        "all_events": all_events,
        "total_events": total_events,
        "total_chapters": total_chapters,
    }
