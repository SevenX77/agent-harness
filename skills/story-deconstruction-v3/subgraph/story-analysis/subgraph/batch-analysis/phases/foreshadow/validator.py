from __future__ import annotations


def _list_of_strings(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ValueError("foreshadow list fields must be arrays")
    return [str(item) for item in value]


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    results = output.get("foreshadow_results") or []
    if not isinstance(results, list):
        raise ValueError("foreshadow_results must be an array")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("foreshadow_results items must be objects")
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("foreshadow result missing event_id")
        normalized.append(
            {
                "event_id": event_id,
                "foreshadowing_id": str(item.get("foreshadowing_id") or ""),
                "description": str(item.get("description") or ""),
                "plant": _list_of_strings(item.get("plant")),
                "payoff": _list_of_strings(item.get("payoff")),
                "plant_event_id": item.get("plant_event_id") or event_id,
                "resolves_foreshadowing_id": str(item.get("resolves_foreshadowing_id") or ""),
                "is_resolved": bool(item.get("is_resolved", False)),
            }
        )
    return {"foreshadow_results": normalized}
