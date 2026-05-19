from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register_entity(name: str, entity_type: str, description: str, initial_state: str, context: dict) -> str:
    registry = context.setdefault('entity_registry', {})
    
    prefix_map = {
        'character': 'CHR',
        'location': 'LOC',
        'prop': 'PRP'
    }
    
    if entity_type not in prefix_map:
        return f'Invalid entity_type: {entity_type}'
    
    prefix = prefix_map[entity_type]
    max_num = 0
    for existing_id in registry.keys():
        if existing_id.startswith(prefix + '_'):
            try:
                num = int(existing_id.split('_')[1])
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                continue
    
    new_num = max_num + 1
    entity_id = f'{prefix}_{new_num:03d}'
    
    registry[entity_id] = {
        'name': name,
        'type': entity_type,
        'description': description,
        'initial_state': initial_state
    }
    
    return f'Registered {entity_id}: {name}'


def resolve_alias(alias: str, canonical_entity_id: str, context: dict) -> str:
    aliases = context.setdefault('entity_aliases', {})
    registry = context.get('entity_registry', {})
    
    if canonical_entity_id not in registry:
        return f'Entity {canonical_entity_id} not found in registry'
    
    aliases[alias] = canonical_entity_id
    entity_name = registry[canonical_entity_id].get('name', 'Unknown')
    return f"Alias '{alias}' -> {canonical_entity_id} ({entity_name})"


def get_entity_registry_summary(context: dict) -> str:
    registry = context.get('entity_registry', {})
    aliases = context.get('entity_aliases', {})
    
    if not registry:
        return 'Entity Registry: Empty'
    
    lines = ['Entity Registry:', '=' * 50]
    
    reverse_aliases = {}
    for alias, entity_id in aliases.items():
        reverse_aliases.setdefault(entity_id, []).append(alias)
    
    for entity_id, data in sorted(registry.items()):
        name = data.get('name', 'Unknown')
        etype = data.get('type', 'unknown')
        desc = data.get('description', '')
        initial = data.get('initial_state', '')
        entity_aliases = reverse_aliases.get(entity_id, [])
        
        lines.append(f'  [{entity_id}] {name} ({etype})')
        lines.append(f'    Description: {desc}')
        lines.append(f'    Initial State: {initial}')
        if entity_aliases:
            lines.append(f'    Aliases: {", ".join(entity_aliases)}')
        lines.append('')
    
    return '\n'.join(lines)
