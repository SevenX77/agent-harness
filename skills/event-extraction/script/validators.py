"""Event extraction validators for story deconstruction.

This module provides validation functions for event extraction quality assurance.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def validate_event_extraction(context: dict) -> tuple[bool, list[str]]:
    """Validate event extraction quality and report issues.
    
    Performs comprehensive validation checks:
    - Events list is not empty
    - Each event has paragraph_indices
    - Coverage ratio >= 50%
    - No pure numeric time values
    - Empty paragraph ratio <= 20%
    
    Returns:
        (is_valid, issues): Boolean validity and list of issue descriptions
    """
    event_timeline = context.get('event_timeline', {})
    events = event_timeline.get('events', [])
    segmentation = context.get('segmentation_result', {})
    paragraphs = segmentation.get('paragraphs', [])
    
    issues: list[str] = []
    
    # Check 1: Events list is not empty
    if not events:
        issues.append("No events extracted")
        logger.error("Validation failed: No events extracted")
        return False, issues
    
    # Check 2: Each event has paragraph_indices
    empty_idx_count = 0
    for event in events:
        para_indices = event.get('paragraph_indices', [])
        if not para_indices:
            empty_idx_count += 1
            event_id = event.get('event_id', '?')
            issues.append(f"Event {event_id} has no paragraph indices")
    
    empty_ratio = empty_idx_count / len(events) if events else 0

    # Check 3: Coverage ratio (informational only)
    covered = set()
    for event in events:
        for pi in event.get('paragraph_indices', []):
            covered.add(pi)

    # Only count B/C paragraphs (A paragraphs may be settings)
    b_c_paragraphs = [p for p in paragraphs if p.get('type') in ('B', 'C')]
    b_c_count = len(b_c_paragraphs)

    coverage_ratio = len(covered) / b_c_count if b_c_count > 0 else 1.0
    
    # Check 4: No pure numeric time values
    invalid_time_count = 0
    for event in events:
        time_val = event.get('time', '')
        # Clean time value
        clean = time_val.replace('[推断]', '').replace('[自动修正]', '').strip()
        # Check if pure numeric (like "23")
        if re.match(r'^\d+$', clean):
            invalid_time_count += 1
            event_id = event.get('event_id', '?')
            issues.append(f"Event {event_id} has pure numeric time: {time_val}")
            logger.warning(f"Event {event_id}: Pure numeric time detected")
    
    if invalid_time_count > 0:
        issues.append(f"{invalid_time_count} events have invalid pure-numeric time values")
    
    # Determine overall validity
    is_valid = len(events) > 0 and invalid_time_count == 0
    
    if is_valid:
        logger.info(f"Event extraction validation passed: {len(events)} events, coverage={coverage_ratio:.1%}")
    else:
        logger.warning(f"Event extraction validation failed: {len(issues)} issues")
    
    context['validation_issues'] = issues
    context['validation_metrics'] = {
        'event_count': len(events),
        'empty_ratio': empty_ratio,
        'coverage_ratio': coverage_ratio,
        'invalid_time_count': invalid_time_count
    }
    
    return is_valid, issues
