from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate and perform global climax ranking, foreshadowing closure and character ranking."""
    batch_outputs = state_slice.get("batch_outputs") or []
    acc = state_slice.get("accumulated_context") or {}
    entity_registry = state_slice.get("entity_registry") or {}
    aliases = acc.get("entity_aliases") or {}

    # 1. rank_climaxes logic
    climaxes = []
    for batch in batch_outputs:
        events = batch.get("events", [])
        for ev in events:
            tension = ev.get("tension", {})
            intensity = tension.get("climax_intensity", 0)
            if intensity and intensity > 0:
                climaxes.append(
                    {
                        "event_id": ev.get("event_id", ""),
                        "climax_intensity": intensity,
                        "climax_type": tension.get("climax_type", ""),
                        "chapter_number": ev.get("chapter_number", 0),
                    }
                )

    if climaxes:
        max_intensity = max(c["climax_intensity"] for c in climaxes)
        min_intensity = min(c["climax_intensity"] for c in climaxes)

        for c in climaxes:
            if max_intensity == min_intensity:
                normalized = 5
            else:
                normalized = (
                    1
                    + (c["climax_intensity"] - min_intensity)
                    / (max_intensity - min_intensity)
                    * 9
                )
            c["climax_intensity"] = clamp(round(normalized, 1), 1, 10)

        climaxes.sort(
            key=lambda x: (
                -x["climax_intensity"],
                x["chapter_number"],
                x["event_id"],
            )
        )

        for rank, c in enumerate(climaxes, 1):
            c["global_rank"] = rank

    # 2. close_foreshadowing logic
    foreshadowing_list = acc.get("open_foreshadowing") or []
    closure_results = []

    for fore in foreshadowing_list:
        if not isinstance(fore, dict):
            continue
        fore_id = fore.get("foreshadowing_id", "")
        has_plant = fore.get("plant_event_id") is not None

        payoff_found = False
        for batch in batch_outputs:
            events = batch.get("events", [])
            for ev in events:
                fores = ev.get("foreshadowing", {})
                if fores.get("resolves_foreshadowing_id") == fore_id:
                    payoff_found = True
                    break
            if payoff_found:
                break

        if payoff_found:
            status = "resolved"
        elif has_plant:
            status = "open"
        else:
            status = "abandoned"

        closure_results.append(
            {
                "foreshadowing_id": fore_id,
                "description": fore.get("description", ""),
                "status": status,
                "plant_event_id": fore.get("plant_event_id"),
                "payoff_found": payoff_found,
            }
        )

    # 3. rank_characters logic
    char_stats = {}
    for batch in batch_outputs:
        events = batch.get("events", [])
        for ev in events:
            char_changes = ev.get("character_changes", {})
            chars = (
                char_changes.get("characters_involved", [])
                if isinstance(char_changes, dict)
                else []
            )

            for char_id in chars:
                canonical_id = aliases.get(char_id, char_id)
                if canonical_id not in char_stats:
                    char_stats[canonical_id] = {
                        "appearances": 0,
                        "changes": 0,
                        "name": char_id,
                    }
                char_stats[canonical_id]["appearances"] += 1

            changes_list = (
                char_changes.get("changes", [])
                if isinstance(char_changes, dict)
                else []
            )
            for change in changes_list:
                if isinstance(change, dict):
                    char_id = change.get("character_id", "")
                else:
                    char_id = str(change).split(":")[0] if ":" in str(change) else str(change)
                canonical_id = aliases.get(char_id, char_id)
                if canonical_id in char_stats:
                    char_stats[canonical_id]["changes"] += 1

    for char_id, stats in char_stats.items():
        if char_id in entity_registry:
            stats["name"] = entity_registry[char_id].get("name", char_id)

    scored_chars = []
    for char_id, stats in char_stats.items():
        score = stats["appearances"] * 1.0 + stats["changes"] * 2.0
        scored_chars.append(
            {
                "character_id": char_id,
                "name": stats["name"],
                "appearances": stats["appearances"],
                "changes": stats["changes"],
                "score": score,
            }
        )

    scored_chars.sort(key=lambda x: -x["score"])

    total = len(scored_chars)
    for rank, char in enumerate(scored_chars):
        percentile = (rank + 1) / total * 100 if total > 0 else 0
        if percentile <= 5:
            char["role_tier"] = "protagonist"
        elif percentile <= 20:
            char["role_tier"] = "main_cast"
        elif percentile <= 35:
            char["role_tier"] = "antagonist"
        elif percentile <= 70:
            char["role_tier"] = "supporting"
        else:
            char["role_tier"] = "minor"
        char["rank"] = rank + 1

    logger.info(
        f"Global synthesis complete: ranked {len(climaxes)} climaxes, ranked {len(scored_chars)} characters"
    )

    return {
        "climax_ranking": climaxes,
        "foreshadowing_closure": closure_results,
        "character_ranking": scored_chars,
    }
