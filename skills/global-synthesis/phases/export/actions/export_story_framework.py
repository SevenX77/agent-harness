from graph_agent.cognitive.context_facade import Context


def export_story_framework(context: Context) -> None:
    """Assemble final story framework artifact from global synthesis fields."""

    global_analysis = context.get("global_analysis", {})
    retroactive = context.get("retroactive", {})
    story_framework = {
        "climax_ranking": global_analysis.get("climax_ranking", ""),
        "foreshadowing_closure": global_analysis.get("foreshadowing_closure", ""),
        "character_ranking": global_analysis.get("character_ranking", ""),
        "unified_event_stream": retroactive.get("corrected_event_stream")
        or context.get("unified_event_stream", []),
        "scenes": context.get("scenes", []),
        "retroactive_corrections": retroactive.get("retroactive_corrections", ""),
    }
    context.set("story_framework", story_framework)
