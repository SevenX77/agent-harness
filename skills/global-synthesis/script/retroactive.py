from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CORRECTABLE_FIELDS = [
    'clothing', 'makeup', 'hygiene', 'injuries',
    'key_relationships', 'social_position',
    'normalized_location', 'lighting_vibe'
]

UNCORRECTABLE_FIELDS = [
    'scene_space_type', 'climax_intensity', 'emotion_type'
]


def scan_anchor_points(context: dict) -> str:
    batch_outputs = context.get('batch_outputs', [])
    corrections = []
    
    all_events = []
    for batch in batch_outputs:
        events = batch.get('events', [])
        all_events.extend(events)
    
    all_events.sort(key=lambda x: (x.get('chapter_number', 0), x.get('event_id', '')))
    
    for idx, ev in enumerate(all_events):
        is_inferred = ev.get('is_inferred', {})
        if not is_inferred:
            continue
        
        for field in CORRECTABLE_FIELDS:
            if field not in is_inferred:
                continue
            
            current_val = ev.get(field, '')
            
            corrected_val = None
            anchor_event_id = None
            
            for later_ev in all_events[idx + 1:]:
                later_inferred = later_ev.get('is_inferred', {})
                if field not in later_inferred or not later_inferred.get(field):
                    corrected_val = later_ev.get(field)
                    anchor_event_id = later_ev.get('event_id')
                    break
            
            if corrected_val is not None and corrected_val != current_val:
                corrections.append({
                    'event_id': ev.get('event_id'),
                    'field': field,
                    'current_value': current_val,
                    'corrected_value': corrected_val,
                    'anchor_event_id': anchor_event_id,
                    'reason': f'Field {field} was inferred at {ev.get("event_id")}, but explicitly defined at {anchor_event_id}'
                })
    
    context['retroactive_corrections'] = corrections
    return f'Found {len(corrections)} retroactive corrections'


def apply_corrections(context: dict) -> str:
    corrections = context.get('retroactive_corrections', [])
    batch_outputs = context.get('batch_outputs', [])
    
    applied_count = 0
    
    for corr in corrections:
        event_id = corr.get('event_id')
        field = corr.get('field')
        new_val = corr.get('corrected_value')
        
        for batch in batch_outputs:
            events = batch.get('events', [])
            for ev in events:
                if ev.get('event_id') == event_id:
                    ev[field] = new_val
                    if 'is_inferred' in ev and field in ev['is_inferred']:
                        ev['is_inferred'][field] = False
                    applied_count += 1
                    break
    
    context['corrections_applied'] = applied_count
    return f'Applied {applied_count} corrections'
