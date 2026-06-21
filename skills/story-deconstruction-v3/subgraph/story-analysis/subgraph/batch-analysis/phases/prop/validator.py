from __future__ import annotations


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    results = output.get("prop_results") or []
    if not isinstance(results, list):
        raise ValueError("prop_results must be an array")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("prop_results items must be objects")
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("prop result missing event_id")
        changes = item.get("changes") or []
        if isinstance(changes, str):
            changes = [changes]
        if not isinstance(changes, list):
            raise ValueError("changes must be an array")
        normalized.append(
            {
                "event_id": event_id,
                "prop_id": str(item.get("prop_id") or item.get("entity_id") or ""),
                "name": str(item.get("name") or ""),
                "changes": [str(value) for value in changes],
                "current_state": str(item.get("current_state") or item.get("state") or ""),
            }
        )
    return {"prop_results": normalized}
