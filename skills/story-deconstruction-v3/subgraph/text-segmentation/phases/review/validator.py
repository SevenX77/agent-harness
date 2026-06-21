from __future__ import annotations

import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate final segments and build the terminal segmentation_result."""
    parsed_segments = output.get("parsed_segments", [])
    chapter_lines = state_slice.get("chapter_lines", [])
    chapter_number = state_slice.get("chapter_number", 0)

    if not parsed_segments:
        raise ValueError("No segments in final output")

    required_fields = ["index", "type", "start_line", "end_line"]

    for seg in parsed_segments:
        seg_index = seg.get("index", "?")

        # Check required fields
        for field in required_fields:
            if seg.get(field) is None:
                raise ValueError(f"Segment {seg_index}: missing required field '{field}'")

        # Check types
        if seg.get("type") not in ("A", "B", "C"):
            raise ValueError(f"Segment {seg_index}: type must be 'A', 'B', or 'C'")

        start = seg.get("start_line")
        end = seg.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError(f"Segment {seg_index}: line numbers must be integers")
        elif start > end:
            raise ValueError(f"Segment {seg_index}: start_line {start} > end_line {end}")

        if not isinstance(seg.get("index"), int):
            raise ValueError(f"Segment {seg_index}: index must be an integer")

    # Check no duplicate indices
    indices = [seg.get("index") for seg in parsed_segments]
    if len(indices) != len(set(indices)):
        duplicates = [idx for idx in set(indices) if indices.count(idx) > 1]
        raise ValueError(f"Duplicate segment indices found: {duplicates}")

    # Re-extract and store segments
    sorted_segs = sorted(parsed_segments, key=lambda s: s.get("start_line", 0))
    segments = []
    for para in sorted_segs:
        start_line = para.get("start_line")
        end_line = para.get("end_line")

        # Convert to 0-based indices
        start_idx = max(start_line - 1, 0)
        end_idx = min(end_line, len(chapter_lines))

        paragraph_lines = chapter_lines[start_idx:end_idx]
        content = "\n".join(paragraph_lines)

        segment = {
            "index": para["index"],
            "type": para["type"],
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
            "description": para.get("description", ""),
        }
        segments.append(segment)

    # Validate text restoration
    original_text = "\n".join(chapter_lines)
    restored_text = "".join([s["content"] for s in segments])
    similarity = SequenceMatcher(None, original_text, restored_text).ratio()

    if similarity < 0.95:
        logger.warning(f"Text restoration diff in review: {(1-similarity)*100:.1f}%")

    # Calculate type distribution
    type_distribution = {"A": 0, "B": 0, "C": 0}
    for seg in segments:
        if seg["type"] in type_distribution:
            type_distribution[seg["type"]] += 1

    # Build result
    segmentation_result = {
        "chapter_number": chapter_number,
        "total_paragraphs": len(segments),
        "paragraphs": segments,
        "metadata": {
            "type_distribution": type_distribution,
            "restoration_similarity": round(similarity, 4),
        },
    }

    return {
        "parsed_segments": parsed_segments,
        "segments": segments,
        "segmentation_result": segmentation_result,
    }
