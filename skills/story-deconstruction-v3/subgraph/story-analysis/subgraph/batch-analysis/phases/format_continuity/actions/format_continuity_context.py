from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _format_result_line(result) -> str:
    if not isinstance(result, dict):
        return f"- {result}"

    event_id = result.get("event_id", "unknown")
    character_id = (
        result.get("character_id")
        or result.get("entity_id")
        or result.get("name")
        or "unknown"
    )
    current_state = result.get("current_state") or result.get("state") or ""
    changes = result.get("changes") or []
    if isinstance(changes, list):
        changes_text = "; ".join(str(item) for item in changes)
    else:
        changes_text = str(changes)

    detail_parts = []
    if current_state:
        detail_parts.append(f"current_state: {current_state}")
    if changes_text:
        detail_parts.append(f"changes: {changes_text}")
    details = "; ".join(detail_parts) if detail_parts else str(result)
    return f"- [{event_id}] {character_id}: {details}"


def format_continuity_context(inputs) -> dict:
    """Format this batch's character analysis results for the continuity prompt.

    Runs after entity_and_characters so character_results reflects the CURRENT
    batch (generating this text in prepare would always read the previous
    batch's leftovers and render an empty placeholder).
    """
    character_results = inputs.get("character_results") or []

    if not character_results:
        logger.warning(
            "format_continuity: no character_results from this batch; "
            "continuity agent will see an explicit empty placeholder"
        )
        return {"batch_character_changes_text": "无本批次角色变化记录。"}

    lines = ["本批次角色变化："]
    for result in character_results:
        lines.append(_format_result_line(result))

    logger.info(
        "format_continuity: formatted %d character results", len(character_results)
    )
    return {"batch_character_changes_text": "\n".join(lines)}
