"""Text segmentation validators (ABC paragraph segmentation).

Phase 2 A1 contract (2026-04-29): validators mounted on LLMPhases receive
``payload: list[dict[str, Any]]`` parsed from the phase's declared
``output_schema`` (``script.models.Segment`` for both ``segment`` and
``review`` phases of ``skills/text-segmentation/SKILL.md``). The
validators below already operated on a list of Segment dicts; this
revision only tightens the type hints so they conform to the strict
contract documented in PHASE2_DESIGN.md §2.4.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def validate_segmentation_structure(
    segments: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Node 02 结构 validator：行号连续性 + confidence 阈值"""
    errors: list[str] = []

    if not segments:
        return (False, ["No segments produced. Re-analyze the chapter text."])
    
    # Check 1: JSON format and required fields
    for seg in segments:
        if not isinstance(seg, dict):
            errors.append(f"Segment is not a dict: {type(seg)}")
            continue
        
        seg_type = seg.get("type")
        if not seg_type or seg_type not in ("A", "B", "C"):
            errors.append(f"Segment {seg.get('index', '?')}: invalid type '{seg_type}'")
        
        if not seg.get("content"):
            errors.append(f"Segment {seg.get('index', '?')}: empty content")
        
        # Confidence threshold check (< 0.7 is an error)
        confidence = seg.get("confidence", 1.0)
        if isinstance(confidence, (int, float)) and confidence < 0.7:
            errors.append(
                f"Segment {seg.get('index', '?')}: confidence {confidence:.2f} < 0.7 threshold"
            )
    
    # Check 2: Line number continuity (100% continuous, no gaps)
    sorted_segs = sorted(segments, key=lambda s: s.get("start_line", 0))
    for i in range(1, len(sorted_segs)):
        prev_end = sorted_segs[i - 1].get("end_line", 0)
        curr_start = sorted_segs[i].get("start_line", 0)
        if curr_start > prev_end + 1:
            errors.append(
                f"Gap between segment {sorted_segs[i-1].get('index')} (end={prev_end}) "
                f"and {sorted_segs[i].get('index')} (start={curr_start})"
            )
    
    if errors:
        return (False, errors)
    return (True, [])


def validate_final_format(
    segments: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Node 03 格式 validator：最终输出格式检查"""
    errors: list[str] = []

    if not segments:
        return (False, ["No segments in final output"])
    
    required_fields = ["index", "type", "content", "start_line", "end_line"]
    optional_fields = ["description", "confidence", "notes"]
    
    for seg in segments:
        seg_index = seg.get("index", "?")
        
        # Check required fields exist
        for field in required_fields:
            if field not in seg:
                errors.append(f"Segment {seg_index}: missing required field '{field}'")
        
        # Check field types
        if seg.get("type") not in ("A", "B", "C"):
            errors.append(f"Segment {seg_index}: type must be 'A', 'B', or 'C'")
        
        if not isinstance(seg.get("content", ""), str):
            errors.append(f"Segment {seg_index}: content must be a string")
        
        start = seg.get("start_line")
        end = seg.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            errors.append(f"Segment {seg_index}: line numbers must be integers")
        elif start > end:
            errors.append(f"Segment {seg_index}: start_line {start} > end_line {end}")
        
        # Check SegmentationResult schema compliance
        if not isinstance(seg.get("index"), int):
            errors.append(f"Segment {seg_index}: index must be an integer")
    
    # Check no duplicate indices
    indices = [seg.get("index") for seg in segments]
    if len(indices) != len(set(indices)):
        duplicates = [idx for idx in set(indices) if indices.count(idx) > 1]
        errors.append(f"Duplicate segment indices found: {duplicates}")
    
    # Check A/B/C type validity
    action_verbs = re.compile(r"(跑|打|杀|追|逃|抓|砍|刺|射|冲|跳)")
    setting_keywords = re.compile(r"(规则|体系|原则|铁律|系统|等级|能力|序列|觉醒|针剂|超凡|诡异)")
    
    for seg in segments:
        seg_type = seg.get("type")
        content = seg.get("content", "")
        seg_idx = seg.get("index", "?")
        
        if seg_type == "A":
            # A-type should have setting keywords
            setting_count = len(setting_keywords.findall(content))
            if setting_count < 1:
                # Not an error, but flag as warning
                pass
        
        # Check for overly long segments (warning only, not blocking)
        sentences = [s.strip() for s in re.split(r"[。！？]", content) if s.strip()]
        if len(sentences) > 30:
            # Only flag as error if extremely long (>30 sentences)
            errors.append(f"Segment {seg_idx}: {len(sentences)} sentences - too long, must split")
    
    if errors:
        return (False, errors)
    return (True, [])
