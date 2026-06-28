from __future__ import annotations


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    results = output.get("system_results") or []
    if not isinstance(results, list):
        raise ValueError("system_results must be an array")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("system_results items must be objects")
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("system result missing event_id")
        parameters = item.get("updated_parameters") or []
        if isinstance(parameters, str):
            parameters = [parameters]
        if not isinstance(parameters, list):
            raise ValueError("updated_parameters must be an array")
        normalized.append(
            {
                "event_id": event_id,
                "system_action": str(item.get("system_action") or ""),
                "updated_parameters": [str(value) for value in parameters],
            }
        )
    return {"system_results": normalized}
