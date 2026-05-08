from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def build_unified_event_stream(context: dict) -> str:
    batch_outputs = context.get("batch_outputs", [])

    all_events = []
    for batch in batch_outputs:
        events = batch.get("events", [])
        all_events.extend(events)

    all_events.sort(key=lambda x: (x.get("chapter_number", 0), x.get("event_id", "")))

    scenes = []
    current_scene = None
    scene_counter = 0

    for ev in all_events:
        spatio = ev.get("spatiotemporal", {})
        tension = ev.get("tension", {})

        location = spatio.get("normalized_location", ev.get("normalized_location", ""))
        day = spatio.get("time_coordinate", {}).get(
            "day", ev.get("time_coordinate", {}).get("day", 0)
        )
        space_type = ev.get("scene_space_type", tension.get("scene_space_type", ""))

        is_new_scene = False
        if current_scene is None:
            is_new_scene = True
        else:
            if location and location != current_scene.get("location"):
                is_new_scene = True
            elif day and day != current_scene.get("day"):
                is_new_scene = True
            elif space_type and space_type != current_scene.get("space_type"):
                is_new_scene = True

        if is_new_scene:
            scene_counter += 1
            current_scene = {
                "scene_id": f"SC{scene_counter:03d}",
                "location": location,
                "day": day,
                "space_type": space_type,
                "characters": [],
                "props": [],
                "event_ids": [],
                "climax_peak": 0,
                "lighting_vibe": tension.get("lighting_vibe", ""),
            }
            scenes.append(current_scene)

        current_scene["event_ids"].append(ev.get("event_id"))

        char_changes = ev.get("character_changes", {})
        chars = (
            char_changes.get("characters_involved", []) if isinstance(char_changes, dict) else []
        )
        current_scene["characters"].extend(chars)

        prop_changes = ev.get("prop_changes", {})
        props = prop_changes.get("props_involved", []) if isinstance(prop_changes, dict) else []
        current_scene["props"].extend(props)

        intensity = tension.get("climax_intensity", 0)
        if isinstance(intensity, (int, float)) and intensity > current_scene["climax_peak"]:
            current_scene["climax_peak"] = intensity

        lighting = tension.get("lighting_vibe", "")
        if lighting:
            current_scene["lighting_vibe"] = lighting

    for scene in scenes:
        scene["characters"] = list(set(scene["characters"]))
        scene["props"] = list(set(scene["props"]))
        del scene["day"]
        del scene["space_type"]

    context["scenes"] = scenes
    context["unified_event_stream"] = all_events
    return f"Built {len(scenes)} scenes from {len(all_events)} events"


def export_story_framework(context: dict) -> str:
    framework = {
        "climax_ranking": context.get("climax_ranking", []),
        "foreshadowing_closure": context.get("foreshadowing_closure", []),
        "character_ranking": context.get("character_ranking", []),
        "scenes": context.get("scenes", []),
        "unified_event_stream": context.get("unified_event_stream", []),
        "entity_registry": context.get("entity_registry", {}),
    }

    context["story_framework"] = framework
    return "Exported story framework"
