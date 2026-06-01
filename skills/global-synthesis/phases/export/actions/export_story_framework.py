import logging

logger = logging.getLogger(__name__)


def export_story_framework(context) -> dict:
    """Export story framework and perform final global synthesis validation."""

    def _validate_global_synthesis(ctx: dict) -> tuple[bool, list[str]]:
        errors = []

        # L1: Check core synthesis outputs exist and are non-empty
        required_items = [
            ("climax_ranking", "climax ranking"),
            ("character_ranking", "character ranking"),
            ("foreshadowing_closure", "foreshadowing closure"),
        ]

        for key, label in required_items:
            if key not in ctx:
                errors.append(f"L1: Missing {label} ({key})")
            elif not ctx[key]:
                errors.append(f"L1: Empty {label} ({key})")

        # L2: Check unified event stream and scenes
        if "unified_event_stream" not in ctx:
            errors.append("L2: Missing unified_event_stream")
        elif not ctx["unified_event_stream"]:
            errors.append("L2: Empty unified_event_stream")

        if "scenes" not in ctx:
            errors.append("L2: Missing scenes")
        elif not ctx["scenes"]:
            errors.append("L2: Empty scenes")

        # L3: Flag abandoned foreshadowing items
        fore_closure = ctx.get("foreshadowing_closure", [])
        for item in fore_closure:
            if item.get("status") == "abandoned":
                fore_id = item.get("foreshadowing_id", "unknown")
                errors.append(f"L3: Abandoned foreshadowing: {fore_id}")

        is_valid = len(errors) == 0
        return is_valid, errors

    # 1. build the final story framework dictionary
    framework = {
        "climax_ranking": context.get("climax_ranking", []),
        "foreshadowing_closure": context.get("foreshadowing_closure", []),
        "character_ranking": context.get("character_ranking", []),
        "scenes": context.get("scenes", []),
        "unified_event_stream": context.get("unified_event_stream", []),
        "entity_registry": context.get("entity_registry", {}),
    }

    context["story_framework"] = framework

    # 2. validate framework quality
    is_valid, errors = _validate_global_synthesis(context)
    if not is_valid:
        raise ValueError(
            f"Global synthesis quality validation failed: {'; '.join(errors)}"
        )

    logger.info("Story framework exported successfully.")

    return {"story_framework": framework}
