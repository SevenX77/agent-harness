from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate and process entity registration and character status analysis."""
    # Retrieve exist registry & aliases
    accumulator_state = state_slice.get("accumulator_state") or {}
    registry = copy.deepcopy(
        state_slice.get("entity_registry")
        or accumulator_state.get("entity_registry")
        or {}
    )
    aliases = copy.deepcopy(
        state_slice.get("entity_aliases")
        or accumulator_state.get("entity_aliases")
        or {}
    )

    raw_entities = output.get("entities") or []
    raw_aliases = output.get("aliases") or []
    raw_character_changes = output.get("character_changes") or []

    prefix_map = {"character": "CHR", "location": "LOC", "prop": "PRP"}

    # 1. register_entity
    for ent in raw_entities:
        name = ent.get("name", "").strip()
        etype = ent.get("type", "").strip()
        desc = ent.get("description", "").strip()
        initial = ent.get("initial_state", "").strip()

        if etype not in prefix_map:
            logger.warning(f"Invalid entity type: {etype}")
            continue

        # Check if already registered by name (deduplicate)
        exists = False
        for eid, data in registry.items():
            if data.get("name") == name and data.get("type") == etype:
                exists = True
                break
        if exists:
            continue

        prefix = prefix_map[etype]
        max_num = 0
        for existing_id in registry.keys():
            if existing_id.startswith(prefix + "_"):
                try:
                    num = int(existing_id.split("_")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    continue
        new_num = max_num + 1
        entity_id = f"{prefix}_{new_num:03d}"

        registry[entity_id] = {
            "name": name,
            "type": etype,
            "description": desc,
            "initial_state": initial,
        }
        logger.info(f"Registered {entity_id}: {name}")

    # Helper mapping to find canonical ID by name
    def find_id_by_name(name_str: str) -> str | None:
        name_str = name_str.strip()
        if not name_str:
            return None
        # Try exact registry match
        for eid, data in registry.items():
            if data.get("name") == name_str:
                return eid
        # Try alias match
        if name_str in aliases:
            return aliases[name_str]
        return None

    # 2. resolve_alias
    for item in raw_aliases:
        alias = item.get("alias", "").strip()
        canonical_name = item.get("canonical_name", "").strip()

        canon_id = find_id_by_name(canonical_name)
        if canon_id:
            aliases[alias] = canon_id
            logger.info(f"Resolved alias '{alias}' -> {canon_id}")

    # 3. character changes analysis & mapping
    character_results = []
    # Temporary to track latest states within this batch
    latest_states_tracker = {}

    # Group by event_id & character
    grouped_changes = {}
    for chg in raw_character_changes:
        ev_id = chg.get("event_id", "")
        char_ref = chg.get("character_id") or chg.get("character_name") or ""
        char_id = find_id_by_name(char_ref) or char_ref

        if not char_id:
            continue

        key = (ev_id, char_id)
        grouped_changes.setdefault(key, []).extend(chg.get("changes", []))

    for (ev_id, char_id), changes in grouped_changes.items():
        changes_str_list = []
        latest_state = ""

        for c in changes:
            field = c.get("field", "")
            from_val = c.get("from", "")
            to_val = c.get("to", "")
            is_inf = c.get("is_inferred", False)

            inf_suffix = " [推断]" if is_inf else ""
            changes_str_list.append(f"{field}: {from_val} -> {to_val}{inf_suffix}")

            # Keep latest status of physical/appearance/clothing state
            if field in ("appearance", "clothing", "state"):
                latest_state = to_val

        char_name = registry.get(char_id, {}).get("name", char_id)

        result_dict = {
            "event_id": ev_id,
            "character_id": char_id,
            "name": char_name,
            "current_state": latest_state or "状态未有重大改变",
            "changes": changes_str_list,
        }
        character_results.append(result_dict)

    return {
        "entity_registry": registry,
        "entity_aliases": aliases,
        "character_results": character_results,
    }
