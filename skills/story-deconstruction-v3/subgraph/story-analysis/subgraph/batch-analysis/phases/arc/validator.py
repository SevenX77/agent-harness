from __future__ import annotations


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    results = output.get("arc_results") or []
    if not isinstance(results, list):
        raise ValueError("arc_results must be an array")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("arc_results items must be objects")
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("arc result missing event_id")
        curve = item.get("curve") or []
        if isinstance(curve, str):
            curve = [curve]
        if not isinstance(curve, list):
            raise ValueError("curve must be an array")
        normalized.append(
            {
                "event_id": event_id,
                "arc_id": str(item.get("arc_id") or ""),
                "curve": [str(value) for value in curve],
                "is_active": bool(item.get("is_active", True)),
            }
        )
    return {"arc_results": normalized}
