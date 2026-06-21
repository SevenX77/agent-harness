from __future__ import annotations


def _bounded_int(value, field: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 0 or value > 10:
        raise ValueError(f"{field} must be between 0 and 10")
    return value


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    results = output.get("tension_results") or []
    if not isinstance(results, list):
        raise ValueError("tension_results must be an array")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("tension_results items must be objects")
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("tension result missing event_id")
        normalized.append(
            {
                "event_id": event_id,
                "climax_intensity": _bounded_int(item.get("climax_intensity", 0), "climax_intensity"),
                "emotion_intensity": _bounded_int(item.get("emotion_intensity", 0), "emotion_intensity"),
                "climax_type": str(item.get("climax_type") or ""),
                "emotion_type": str(item.get("emotion_type") or ""),
                "lighting_vibe": str(item.get("lighting_vibe") or ""),
            }
        )
    return {"tension_results": normalized}
