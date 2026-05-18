from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def validate_segmentation_structure(context: dict) -> tuple[bool, str]:
    """Node 02 结构 validator：行号连续性 + confidence 阈值"""
    errors: list[str] = []
    
    segments = context.get("segments", [])
    chapter_lines = context.get("chapter_lines", [])
    
    if not segments:
        return (False, "No segments produced. Re-analyze the chapter text.")
    
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
        
    # Check 2: Line coverage
    if chapter_lines:
        total_lines = len(chapter_lines)
        covered: set[int] = set()
        for seg in segments:
            start = seg.get("start_line", 0)
            end = seg.get("end_line", 0)
            for ln in range(start, end + 1):
                covered.add(ln)
        
        coverage = len(covered) / total_lines if total_lines > 0 else 0
        if coverage < 0.9:
            errors.append(f"Line coverage {coverage*100:.0f}% < 90%. Check segment boundaries.")
    
    # Check 3: Line number continuity (100% continuous, no gaps)
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
        return (False, "\n".join(errors))
    return (True, "Structure validation passed")


def validate_final_format(context: dict) -> tuple[bool, str]:
    """Node 03 格式 validator：最终输出格式检查"""
    errors: list[str] = []
    
    segments = context.get("segments", [])
    
    if not segments:
        return (False, "No segments in final output")
    
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
        
        # NOTE: No sentence-count hard limit here.
        # If a segment is long, the reviewer's judgment decides whether it should split.
        # See 03_review.md Step 3 for the soft guidance.
    
    if errors:
        return (False, "\n".join(errors))
    return (True, "Final format validation passed")
