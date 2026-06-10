from __future__ import annotations

import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate segment structure and enrich output with segments text extraction."""
    parsed_segments = output.get("parsed_segments", [])
    chapter_lines = state_slice.get("chapter_lines", [])
    chapter_number = state_slice.get("chapter_number", 0)

    if not parsed_segments:
        raise ValueError("No segments produced. Re-analyze the chapter text.")

    # 1. Check basic format & types
    for seg in parsed_segments:
        if not isinstance(seg, dict):
            raise ValueError(f"Segment is not a dict: {type(seg)}")

        seg_type = seg.get("type")
        if not seg_type or seg_type not in ("A", "B", "C"):
            raise ValueError(f"Segment {seg.get('index', '?')}: invalid type '{seg_type}'")

        if seg.get("start_line") is None or seg.get("end_line") is None:
            raise ValueError(f"Segment {seg.get('index', '?')}: missing start_line or end_line")

    # 2. Check Line coverage
    if chapter_lines:
        total_lines = len(chapter_lines)
        covered = set()
        for seg in parsed_segments:
            start = seg.get("start_line", 0)
            end = seg.get("end_line", 0)
            for ln in range(start, end + 1):
                covered.add(ln)

        coverage = len(covered) / total_lines if total_lines > 0 else 0
        if coverage < 0.9:
            raise ValueError(
                f"Line coverage {coverage*100:.0f}% < 90%. Check segment boundaries."
            )

    # 3. Check Line number continuity (100% continuous, no gaps)
    sorted_segs = sorted(parsed_segments, key=lambda s: s.get("start_line", 0))
    for i in range(1, len(sorted_segs)):
        prev_end = sorted_segs[i - 1].get("end_line", 0)
        curr_start = sorted_segs[i].get("start_line", 0)
        if curr_start > prev_end + 1:
            raise ValueError(
                f"Gap between segment {sorted_segs[i-1].get('index')} (end={prev_end}) "
                f"and {sorted_segs[i].get('index')} (start={curr_start})"
            )

    # 4. Store/Extract segment text (equivalent to old store_segments)
    segments = []
    for para in sorted_segs:
        start_line = para.get("start_line")
        end_line = para.get("end_line")

        # Convert to 0-based indices
        start_idx = max(start_line - 1, 0)
        end_idx = min(end_line, len(chapter_lines))

        if start_idx >= len(chapter_lines):
            logger.warning(f"Segment {para['index']} start line out of bounds")
            continue

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
        logger.warning(f"Text restoration diff: {(1-similarity)*100:.1f}%")

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

    # Build human-readable summary for review phase
    summary_lines = [f"# 第{chapter_number}章分段总览"]
    for seg in segments:
        type_label = {"A": "A类-设定", "B": "B类-事件", "C": "C类-系统"}.get(
            seg["type"], seg["type"]
        )
        summary_lines.append(
            f"- **段落{seg['index']}（{type_label}）**：{seg.get('description', '')} "
            f"行号：{seg['start_line']}-{seg['end_line']}"
        )
    segments_summary = "\n".join(summary_lines)

    return {
        "parsed_segments": parsed_segments,
        "segments": segments,
        "segmentation_result": segmentation_result,
        "segments_summary": segments_summary,
    }
