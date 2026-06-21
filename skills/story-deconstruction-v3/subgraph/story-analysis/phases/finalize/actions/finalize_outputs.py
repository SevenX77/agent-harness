from __future__ import annotations


def finalize_outputs(inputs) -> dict:
    """Split the loop accumulator into the three public story-analysis fields."""
    analysis_state = inputs.get("analysis_state") or {}
    batch_outputs = analysis_state.get("batch_history") or []

    return {
        "batch_outputs": batch_outputs,
        "accumulated_context": analysis_state,
        "entity_registry": analysis_state.get("entity_registry", {}),
    }
