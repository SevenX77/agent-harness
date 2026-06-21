from __future__ import annotations


_SPACE_TYPES = {"interior", "exterior", "mixed", ""}


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    results = output.get("spatiotemporal_results") or []
    if not isinstance(results, list):
        raise ValueError("spatiotemporal_results must be an array")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("spatiotemporal_results items must be objects")
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("spatiotemporal result missing event_id")
        scene_space_type = str(item.get("scene_space_type") or "")
        if scene_space_type not in _SPACE_TYPES:
            raise ValueError(f"invalid scene_space_type: {scene_space_type}")
        normalized.append(
            {
                "event_id": event_id,
                "normalized_location": str(item.get("normalized_location") or ""),
                "location": str(item.get("location") or item.get("normalized_location") or ""),
                "scene_space_type": scene_space_type,
                "time_desc": str(item.get("time_desc") or ""),
                "timestamp": str(item.get("timestamp") or ""),
            }
        )
    return {"spatiotemporal_results": normalized}
