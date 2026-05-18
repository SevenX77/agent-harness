from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_batch_analysis(ctx: dict) -> tuple[bool, list[str]]:
    errors = []
    
    # Layer 1: Check non-empty results
    required_results = [
        'tension_results',
        'character_results', 
        'prop_results',
        'arc_results',
        'foreshadowing_results',
        'spatiotemporal_results',
        'system_results'
    ]
    
    for key in required_results:
        if key not in ctx or not ctx[key]:
            errors.append(f'Layer 1: Missing or empty {key}')
    
    
    is_valid = len(errors) == 0
    return is_valid, errors
