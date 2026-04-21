from __future__ import annotations

import logging
import json
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.llm_utils import safe_parse_json_list, clamp, safe_get_str, safe_get_list


def _load_prompt(filename: str) -> dict:
    import yaml
    prompt_dir = Path(__file__).parent.parent / 'prompts'
    with open(prompt_dir / filename, encoding='utf-8') as f:
        return yaml.safe_load(f)


def format_batch_events(context: dict) -> str:
    events = context.get('batch_events', [])
    if not events:
        context['batch_events_text'] = ''
        return 'No events to format'

    lines = []
    for ev in events:
        ev_id = ev.get('event_id', 'unknown')
        ev_type = ev.get('event_type', 'unknown')
        content = ev.get('content', '')
        lines.append(f"[{ev_id}] ({ev_type}): {content}")

    context['batch_events_text'] = '\n'.join(lines)
    return f'Formatted {len(events)} events'


def analyze_tension_emotion_vibe(context: dict) -> str:
    prompt = _load_prompt('tension_emotion_vibe.yaml')
    events_text = context.get('batch_events_text', '')
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'tension_emotion_vibe')

    for r in results:
        r['climax_intensity'] = clamp(r.get('climax_intensity', 0), 0, 10)
        r['emotion_intensity'] = clamp(r.get('emotion_intensity', 0), 0, 10)

    context['tension_results'] = results
    return f'Analyzed {len(results)} items'


def analyze_system_evolution(context: dict) -> str:
    events = context.get('batch_events', [])
    c_events = [e for e in events if e.get('event_type') == 'C']
    if not c_events:
        context['system_results'] = []
        return 'No C-type events to analyze'

    prompt = _load_prompt('system_evolution.yaml')
    events_text = '\n'.join(
        f"[{e.get('event_id', 'unknown')}] {e.get('content', '')}"
        for e in c_events
    )
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'system_evolution')
    context['system_results'] = results
    return f'Analyzed {len(results)} items'


def analyze_character_changes(context: dict) -> str:
    prompt = _load_prompt('character_changes.yaml')
    events_text = context.get('batch_events_text', '')
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'character_changes')
    context['character_results'] = results
    return f'Analyzed {len(results)} items'


def analyze_prop_changes(context: dict) -> str:
    prompt = _load_prompt('prop_changes.yaml')
    events_text = context.get('batch_events_text', '')
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'prop_changes')
    context['prop_results'] = results
    return f'Analyzed {len(results)} items'


def analyze_emotional_arcs(context: dict) -> str:
    prompt = _load_prompt('emotional_arcs.yaml')
    events_text = context.get('batch_events_text', '')
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'emotional_arcs')
    context['arc_results'] = results
    return f'Analyzed {len(results)} items'


def analyze_foreshadowing(context: dict) -> str:
    prompt = _load_prompt('foreshadowing.yaml')
    events_text = context.get('batch_events_text', '')
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'foreshadowing')
    context['foreshadowing_results'] = results
    return f'Analyzed {len(results)} items'


def analyze_spatiotemporal(context: dict) -> str:
    prompt = _load_prompt('spatiotemporal.yaml')
    events_text = context.get('batch_events_text', '')
    acc_text = context.get('accumulated_context_text', '')
    user_msg = f'Events:\n{events_text}\n\nAccumulated:\n{acc_text}'

    llm_call = context.get('_llm_call')
    if not llm_call:
        logger.warning('No _llm_call available')
        return 'No LLM available'

    raw = llm_call(prompt['system'], user_msg, max_tokens=8000)
    results = safe_parse_json_list(raw, 'spatiotemporal')
    context['spatiotemporal_results'] = results
    return f'Analyzed {len(results)} items'


def assemble_batch_results(context: dict) -> str:
    events = context.get('batch_events', [])
    if not events:
        context['batch_result'] = []
        return 'No events to assemble'

    tension = {r.get('event_id', ''): r for r in context.get('tension_results', [])}
    system = {r.get('event_id', ''): r for r in context.get('system_results', [])}
    character = {r.get('event_id', ''): r for r in context.get('character_results', [])}
    prop = {r.get('event_id', ''): r for r in context.get('prop_results', [])}
    arc = {r.get('event_id', ''): r for r in context.get('arc_results', [])}
    foreshadowing = {r.get('event_id', ''): r for r in context.get('foreshadowing_results', [])}
    spatiotemporal = {r.get('event_id', ''): r for r in context.get('spatiotemporal_results', [])}

    merged = []
    for ev in events:
        ev_id = ev.get('event_id', '')
        elements = {
            'character_evolution': character.get(ev_id, {}).get('changes', []),
            'prop_evolution': prop.get(ev_id, {}).get('changes', []),
            'emotion_curve': arc.get(ev_id, {}).get('curve', []),
        }

        merged_ev = {
            'event_id': ev_id,
            'event_type': ev.get('event_type', ''),
            'content': ev.get('content', ''),
            'tension': tension.get(ev_id, {}),
            'system_evolution': system.get(ev_id, {}),
            'character_changes': character.get(ev_id, {}),
            'prop_changes': prop.get(ev_id, {}),
            'emotional_arc': arc.get(ev_id, {}),
            'foreshadowing': foreshadowing.get(ev_id, {}),
            'spatiotemporal': spatiotemporal.get(ev_id, {}),
            'elements': elements,
        }
        merged.append(merged_ev)

    context['batch_result'] = merged
    return f'Assembled {len(merged)} events'
