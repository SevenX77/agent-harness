from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def validate_global_synthesis(ctx: dict) -> tuple[bool, list[str]]:
    errors = []
    
    # L1: Check core synthesis outputs exist and are non-empty
    required_items = [
        ('climax_ranking', 'climax ranking'),
        ('character_ranking', 'character ranking'),
        ('foreshadowing_closure', 'foreshadowing closure')
    ]
    
    for key, label in required_items:
        if key not in ctx:
            errors.append(f'L1: Missing {label} ({key})')
        elif not ctx[key]:
            errors.append(f'L1: Empty {label} ({key})')
    
    # L2: Check unified event stream and scenes
    if 'unified_event_stream' not in ctx:
        errors.append('L2: Missing unified_event_stream')
    elif not ctx['unified_event_stream']:
        errors.append('L2: Empty unified_event_stream')
    
    if 'scenes' not in ctx:
        errors.append('L2: Missing scenes')
    elif not ctx['scenes']:
        errors.append('L2: Empty scenes')
    
    # L3: Flag abandoned foreshadowing items
    fore_closure = ctx.get('foreshadowing_closure', [])
    for item in fore_closure:
        if item.get('status') == 'abandoned':
            fore_id = item.get('foreshadowing_id', 'unknown')
            errors.append(f'L3: Abandoned foreshadowing: {fore_id}')
    
    is_valid = len(errors) == 0
    return is_valid, errors
