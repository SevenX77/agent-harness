from graph_agent.cognitive.context_facade import Context


def assemble_batch(context: Context) -> None:
    """Assemble SKILL phase outputs into final batch artifacts."""

    entity = context.get("entity_and_characters", {})
    parallel = context.get("parallel_analysis", {})
    continuity = context.get("continuity", {})
    accumulated = dict(context.get("accumulated_context", {}) or {})

    batch_result = {
        "entity_and_characters": entity,
        "parallel_analysis": parallel,
        "continuity": continuity,
        "batch_event_count": context.get("batch_event_count", 0),
        "chapter_range": context.get("chapter_range", []),
    }
    updated_accumulated = {
        **accumulated,
        "last_batch_result": batch_result,
        "entity_registry": entity.get("entity_registry", accumulated.get("entity_registry", {}))
        if isinstance(entity, dict)
        else accumulated.get("entity_registry", {}),
    }
    context.update(batch_result=batch_result, updated_accumulated=updated_accumulated)
