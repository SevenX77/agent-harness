"""Text segmentation tools for story deconstruction.

This module provides graph_agent-compatible tool functions for:
- Preparing chapter text with line numbers
- Parsing LLM segmentation output
- Storing and validating segments
- Logging ambiguous segmentations
- Detecting scene breaks for validation
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def prepare_chapter(context: dict) -> str:
    """Prepare chapter text with line numbers for LLM segmentation.
    
    Reads chapter_content and chapter_number from context, adds line numbers,
    and stores preparation metadata back in context.
    """
    chapter_content = context.get('chapter_content', '')
    chapter_number = context.get('chapter_number', 0)
    
    lines = chapter_content.split('\n')
    chapter_with_line_numbers = '\n'.join(
        [f"{i+1:4d}| {line}" for i, line in enumerate(lines)]
    )
    
    context['chapter_with_line_numbers'] = chapter_with_line_numbers
    context['chapter_lines'] = lines
    context['chapter_number'] = chapter_number
    
    logger.info("Prepared chapter %s with %d lines", chapter_number, len(lines))
    return "Chapter %s prepared with %d lines" % (chapter_number, len(lines))


def parse_segmentation_output(raw_output: str, context: dict) -> str:
    """Parse LLM segmentation markdown output.
    
    Extracts paragraph index, type (A/B/C), description, and line ranges from markdown.
    Supports two formats:
    1. Inline: - **段落1（A类-设定）**：描述 行号：1-5
    2. Separate line: description on one line, 行号 on next line
    """
    parsed_segments = []
    lines = raw_output.split('\n')
    current_paragraph = None
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Match paragraph header with optional inline line range:
        # - **段落1（A类-设定）**：描述 行号：1-5
        # - **段落1（A类-设定）**：描述内容 行号：1-16
        para_match = re.match(
            r'^\- \*\*段落(\d+)（([ABC])类.*?）\*\*：(.+)$',
            line_stripped
        )
        
        if para_match:
            if current_paragraph:
                parsed_segments.append(current_paragraph)
            
            desc_part = para_match.group(3).strip()
            start_line = None
            end_line = None
            
            # Try to extract line range from description part (inline format)
            # Pattern: "描述内容 行号：1-16" or "描述 行号: 1-5"
            inline_range = re.search(
                r'(.+?)\s*行号[：:]\s*(\d+)\s*[-–—~至到]\s*(\d+)\s*$',
                desc_part
            )
            
            if inline_range:
                description = inline_range.group(1).strip()
                start_line = int(inline_range.group(2))
                end_line = int(inline_range.group(3))
            else:
                description = desc_part
            
            current_paragraph = {
                "index": int(para_match.group(1)),
                "type": para_match.group(2),
                "description": description,
                "start_line": start_line,
                "end_line": end_line
            }
            continue
        
        # Match line range on separate line (backward compatibility):
        # 行号: 1-5  or  行号：1-16
        if current_paragraph and current_paragraph["start_line"] is None:
            range_match = re.match(
                r'^\s*行号[：:]\s*(\d+)\s*[-–—~至到]\s*(\d+)',
                line_stripped
            )
            if not range_match:
                # Fallback: just look for X-Y pattern
                range_match = re.search(r'(\d+)\s*[-–—~至到]\s*(\d+)', line_stripped)
            
            if range_match:
                current_paragraph["start_line"] = int(range_match.group(1))
                current_paragraph["end_line"] = int(range_match.group(2))
    
    if current_paragraph:
        parsed_segments.append(current_paragraph)
    
    # Validate all segments have line numbers
    for para in parsed_segments:
        if para["start_line"] is None or para["end_line"] is None:
            logger.warning(f"Segment {para['index']} missing line numbers, using defaults")
            # Try to infer from index as fallback
            para["start_line"] = para.get("start_line", para["index"])
            para["end_line"] = para.get("end_line", para["index"])
    
    # Deduplicate: keep last occurrence of each index
    seen_indices = {}
    for para in parsed_segments:
        seen_indices[para["index"]] = para
    parsed_segments = sorted(seen_indices.values(), key=lambda p: p["index"])
    
    context['parsed_segments'] = parsed_segments
    context['raw_segmentation'] = raw_output
    
    logger.info(f"Parsed {len(parsed_segments)} segments")
    return f"Parsed {len(parsed_segments)} segments"


def store_segments(context: dict) -> str:
    """Store final segments with content extracted from chapter lines.
    
    Extracts actual text content for each segment, validates restoration,
    and builds the final segmentation result.
    """
    parsed_segments = context.get('parsed_segments', [])
    chapter_lines = context.get('chapter_lines', [])
    chapter_number = context.get('chapter_number', 0)
    
    segments = []
    for para in parsed_segments:
        start_line = para.get('start_line')
        end_line = para.get('end_line')
        
        # Handle None values with defaults
        if start_line is None:
            start_line = para.get('index', 1)
            logger.warning(f"Segment {para['index']}: start_line was None, using {start_line}")
        if end_line is None:
            end_line = start_line
            logger.warning(f"Segment {para['index']}: end_line was None, using {end_line}")
        
        # Convert to 0-based indices
        start_idx = max(start_line - 1, 0)
        end_idx = min(end_line, len(chapter_lines))
        
        if start_idx >= len(chapter_lines):
            logger.warning(f"Segment {para['index']} start line out of bounds")
            continue
        
        paragraph_lines = chapter_lines[start_idx:end_idx]
        content = '\n'.join(paragraph_lines)
        
        segment = {
            "index": para["index"],
            "type": para["type"],
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
            "description": para.get("description", "")
        }
        segments.append(segment)
    
    # Validate text restoration
    original_text = '\n'.join(chapter_lines)
    restored_text = ''.join([s["content"] for s in segments])
    similarity = SequenceMatcher(None, original_text, restored_text).ratio()
    
    if similarity < 0.95:
        logger.warning(f"Text restoration diff: {(1-similarity)*100:.1f}%")
    else:
        logger.info("Text restoration validation passed")
    
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
            "restoration_similarity": round(similarity, 4)
        }
    }
    
    context['segments'] = segments
    context['segmentation_result'] = segmentation_result
    
    logger.info(f"Stored {len(segments)} segments for chapter {chapter_number}")
    return f"Stored {len(segments)} segments with {type_distribution}"


def log_ambiguous_segments(segment_index: int, reason: str, confidence: float, context: dict) -> str:
    """Log ambiguous segmentation decisions for review.
    
    Records uncertain decisions for layer 3 annotation validation.
    """
    if '_ambiguity_reports' not in context:
        context['_ambiguity_reports'] = []
    
    report = {
        "segment_index": segment_index,
        "reason": reason,
        "confidence": confidence,
        "layer": "L3_annotation"
    }
    context['_ambiguity_reports'].append(report)
    
    logger.warning(f"Ambiguous segment {segment_index}: {reason} (confidence: {confidence})")
    return f"Logged ambiguity for segment {segment_index}"


def detect_scene_breaks(content: str, context: dict) -> str:
    """Detect scene breaks in text for validation.
    
    Identifies temporal and spatial transitions that may indicate segment boundaries.
    Only counts breaks after 20% of content to avoid false positives.
    """
    time_patterns = [
        r'夜幕降临',
        r'天亮了|天边.*亮',
        r'第二天|次日|翌日',
        r'几[天个小]时[后之]',
        r'[早晚]上|[上下]午|傍晚|黎明|凌晨',
        r'一[刻会]儿[后之]',
        r'过了[很好]久',
    ]
    
    space_patterns = [
        r'来到了?|走[进到]了?|回到了?',
        r'离开了?',
        r'抵达|到达',
        r'转移到|前往',
    ]
    
    breaks = 0
    lines = content.split('\n')
    total_lines = len(lines)
    
    for i, line in enumerate(lines):
        # Only count breaks after 20% of content
        if i < total_lines * 0.2:
            continue
        
        line_stripped = line.strip()
        for pattern in time_patterns + space_patterns:
            if re.search(pattern, line_stripped):
                breaks += 1
                break
    
    logger.info(f"Detected {breaks} scene breaks in {total_lines} lines")
    return f"Detected {breaks} scene breaks"


def validate_segmentation(context: dict) -> tuple[bool, list[str]]:
    """Validate segmentation quality and report ambiguities.
    
    Performs Layer 3 annotation validation:
    - Detects overly long paragraphs (>15 sentences)
    - Identifies boundary cases: A-class with narrative verbs below threshold
    - Records findings to context['_ambiguity_reports']
    
    Returns:
        (is_valid, ambiguity_list): Boolean validity and list of ambiguity descriptions
    """
    segments = context.get('segments', [])
    ambiguity_reports = context.get('_ambiguity_reports', [])
    
    # Narrative verbs that suggest B-class content
    narrative_verbs = [
        '走', '跑', '跳', '说', '问', '答', '看', '听', '想', '拿', '给', '来', '去',
        '进', '出', '站', '坐', '躺', '笑', '哭', '喊', '叫', '推', '拉', '打', '踢',
        '飞', '爬', '追', '逃'
    ]
    
    is_valid = True
    ambiguities: list[str] = []
    
    for seg in segments:
        seg_idx = seg.get('index', 0)
        seg_type = seg.get('type', '')
        content = seg.get('content', '')
        description = seg.get('description', '')
        
        # Check 1: Overly long paragraphs (>15 sentences)
        sentences = re.split(r'[。！？\.\!\?]', content)
        sentence_count = len([s for s in sentences if s.strip()])
        if sentence_count > 15:
            is_valid = False
            msg = f'Segment {seg_idx}: Overly long ({sentence_count} sentences > 15)'
            ambiguities.append(msg)
            report = {
                'segment_index': seg_idx,
                'reason': 'overly_long_paragraph',
                'details': f'{sentence_count} sentences exceeds threshold of 15',
                'confidence': 0.95,
                'layer': 'L3_annotation'
            }
            ambiguity_reports.append(report)
            logger.warning(msg)
        
        # Check 2: A-class with narrative verbs (boundary case)
        if seg_type == 'A':
            verb_count = sum(1 for verb in narrative_verbs if verb in content)
            # Below threshold but present - boundary case
            if 0 < verb_count < 3:
                msg = f'Segment {seg_idx}: A-class contains {verb_count} narrative verbs (boundary case)'
                ambiguities.append(msg)
                report = {
                    'segment_index': seg_idx,
                    'reason': 'a_class_narrative_boundary',
                    'details': f'{verb_count} narrative verbs found in A-class segment',
                    'confidence': 0.7,
                    'layer': 'L3_annotation'
                }
                ambiguity_reports.append(report)
                logger.warning(msg)
    
    # Update context
    context['_ambiguity_reports'] = ambiguity_reports
    
    if is_valid and not ambiguities:
        logger.info('Segmentation validation passed')
    elif is_valid:
        logger.info(f'Segmentation valid with {len(ambiguities)} warnings')
    else:
        logger.warning(f'Segmentation invalid: {len(ambiguities)} issues found')
    
    return is_valid, ambiguities
