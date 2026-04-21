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
    
    # Layer 2: Dimension coverage thresholds
    tension_results = ctx.get('tension_results', [])
    total = len(tension_results)
    
    if total > 0:
        # characters_involved >= 40%
        chars_count = sum(1 for r in tension_results if r.get('characters_involved'))
        chars_pct = chars_count / total * 100
        if chars_pct < 40:
            errors.append(f'Layer 2: characters_involved coverage {chars_pct:.1f}% < 40%')
        
        # emotion_intensity >= 90%
        emotion_count = sum(1 for r in tension_results if r.get('emotion_intensity') is not None)
        emotion_pct = emotion_count / total * 100
        if emotion_pct < 90:
            errors.append(f'Layer 2: emotion_intensity coverage {emotion_pct:.1f}% < 90%')
        
        # emotion_type >= 90%
        emotion_type_count = sum(1 for r in tension_results if r.get('emotion_type'))
        emotion_type_pct = emotion_type_count / total * 100
        if emotion_type_pct < 90:
            errors.append(f'Layer 2: emotion_type coverage {emotion_type_pct:.1f}% < 90%')
        
        # lighting_vibe >= 80%
        lighting_count = sum(1 for r in tension_results if r.get('lighting_vibe'))
        lighting_pct = lighting_count / total * 100
        if lighting_pct < 80:
            errors.append(f'Layer 2: lighting_vibe coverage {lighting_pct:.1f}% < 80%')
        
        # scene_space_type >= 90%
        scene_count = sum(1 for r in tension_results if r.get('scene_space_type'))
        scene_pct = scene_count / total * 100
        if scene_pct < 90:
            errors.append(f'Layer 2: scene_space_type coverage {scene_pct:.1f}% < 90%')
    
    # Layer 3: Flag low-confidence entity matches
    char_results = ctx.get('character_results', [])
    for r in char_results:
        confidence = r.get('match_confidence', 1.0)
        if isinstance(confidence, (int, float)) and confidence < 0.7:
            entity_id = r.get('character_id', r.get('entity_id', 'unknown'))
            errors.append(f"Layer 3: Low confidence entity match for {entity_id} ({confidence})")
    
    prop_results = ctx.get('prop_results', [])
    for r in prop_results:
        confidence = r.get('match_confidence', 1.0)
        if isinstance(confidence, (int, float)) and confidence < 0.7:
            entity_id = r.get('prop_id', r.get('entity_id', 'unknown'))
            errors.append(f"Layer 3: Low confidence prop match for {entity_id} ({confidence})")
    
    is_valid = len(errors) == 0
    return is_valid, errors
