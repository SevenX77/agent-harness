import logging

logger = logging.getLogger(__name__)


def segment_all_chapters(inputs) -> dict:
    """Build deterministic segmentation records without nested skill orchestration."""
    chapters = inputs.get("chapters", [])
    all_segmentations = []

    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        content = chapter.get("content", "")
        paragraphs = chapter.get("paragraphs")
        if not isinstance(paragraphs, list):
            paragraphs = [
                {
                    "index": 1,
                    "type": "B",
                    "content": content,
                    "start_line": 0,
                    "end_line": 0,
                    "description": "",
                }
            ] if content else []
        segmentation_result = {
            "chapter_number": chapter_number,
            "total_paragraphs": len(paragraphs),
            "paragraphs": paragraphs,
            "metadata": {"source": "story-deconstruction"},
        }

        all_segmentations.append({
            "chapter_number": chapter_number,
            "segmentation": segmentation_result,
        })

    logger.info(f"Segmented {len(chapters)} chapters into {len(all_segmentations)} segmentations")
    return {"all_segmentations": all_segmentations}
