from __future__ import annotations


def finalize_outputs(inputs) -> dict:
    """Restore batch wrappers and expose the entity registry."""
    accumulated_context = inputs.get("accumulated_context") or {}
    event_batches = inputs.get("event_batches") or []
    batch_outputs_raw = inputs.get("batch_outputs_raw") or []

    if len(event_batches) != len(batch_outputs_raw):
        raise ValueError(
            "event_batches and batch_outputs_raw length mismatch: "
            f"{len(event_batches)} != {len(batch_outputs_raw)}"
        )

    batch_outputs = []
    for index, event_batch in enumerate(event_batches):
        batch_outputs.append(
            {
                "batch_index": event_batch.get("batch_index"),
                "chapter_range": event_batch.get("chapter_range"),
                "events": batch_outputs_raw[index],
            }
        )

    return {
        "entity_registry": accumulated_inputs.get("entity_registry", {}),
        "batch_outputs": batch_outputs,
    }
