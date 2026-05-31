from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel

from story_forge.core.md_parser import md_to_json

logger = logging.getLogger(__name__)


class Setting(BaseModel):
    """One world-setting entry extracted from story paragraphs."""

    setting_id: str = ""
    setting_title: str = ""
    paragraph_index: int = 0
    related_event: int = 0
    setting_summary: str = ""


def _calculate_type_distribution(events: list[dict]) -> dict[str, int]:
    distribution = {"A": 0, "B": 0, "C": 0, "M": 0}
    for event in events:
        event_type = event.get("event_type") or event.get("type") or "B"
        if event_type in distribution:
            distribution[event_type] += 1
    return distribution


def validate_event_extraction(
    event_timeline: dict, paragraphs: list[dict]
) -> tuple[bool, list[str]]:
    """Validate event extraction quality and report issues."""
    events = event_timeline.get("events", [])
    issues: list[str] = []

    # Check 1: Events list is not empty
    if not events:
        issues.append("No events extracted")
        return False, issues

    # Check 2: Each event has paragraph_indices
    empty_idx_count = 0
    for event in events:
        para_indices = event.get("paragraph_indices", [])
        if not para_indices:
            empty_idx_count += 1
            event_id = event.get("event_id", "?")
            issues.append(f"Event {event_id} has no paragraph indices")

    # Check 3: No pure numeric time values
    invalid_time_count = 0
    for event in events:
        time_val = event.get("time", "")
        # Clean time value
        clean = (
            str(time_val).replace("[推断]", "").replace("[自动修正]", "").strip()
        )
        if re.match(r"^\d+$", clean):
            invalid_time_count += 1
            event_id = event.get("event_id", "?")
            issues.append(f"Event {event_id} has pure numeric time: {time_val}")

    if invalid_time_count > 0:
        issues.append(
            f"{invalid_time_count} events have invalid pure-numeric time values"
        )

    is_valid = len(events) > 0 and invalid_time_count == 0
    return is_valid, issues


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate, parse settings and finalize event timeline extraction."""
    raw_markdown = output.get("raw_settings_markdown", "")

    # 1. Parse settings
    setting_items = (
        md_to_json(raw_markdown, Setting) if raw_markdown.strip() else []
    )
    parsed_settings = [item.model_dump() for item in setting_items]

    # Get event_timeline from previous phase state
    event_timeline = copy_timeline(state_slice.get("event_timeline", {}))
    events = event_timeline.get("events", [])

    # 2. Merge settings into events
    owned = {}
    for idx, ev in enumerate(events):
        for pi in ev.get("paragraph_indices", []):
            owned[pi] = idx

    for st in parsed_settings:
        related_event = st.get("related_event")
        if not related_event or related_event < 1 or related_event > len(events):
            continue

        target_idx = related_event - 1
        target = events[target_idx]

        setting_item = {
            "setting_id": st.get("setting_id", ""),
            "setting_title": st.get("setting_title", ""),
            "setting_summary": st.get("setting_summary", ""),
            "paragraph_indices": (
                [st.get("paragraph_index", 0)] if st.get("paragraph_index") else []
            ),
        }

        if "setting" not in target:
            target["setting"] = []
        target["setting"].append(setting_item)

        para_idx = st.get("paragraph_index", 0)
        if para_idx:
            if para_idx in owned and owned[para_idx] != target_idx:
                logger.warning(f"Setting paragraph {para_idx} already owned")
                continue
            if para_idx not in target.get("paragraph_indices", []):
                target["paragraph_indices"].append(para_idx)
                owned[para_idx] = target_idx

        target["paragraph_indices"] = sorted(target["paragraph_indices"])

    # 3. Finalize timeline
    event_timeline["events"] = events
    event_timeline["total_events"] = len(events)
    event_timeline["metadata"]["type_distribution"] = _calculate_type_distribution(
        events
    )

    segmentation = state_slice.get("segmentation_result", {})
    paragraphs = segmentation.get("paragraphs", [])

    # 4. Perform final schema & quality validation
    is_valid, issues = validate_event_extraction(event_timeline, paragraphs)
    if not is_valid:
        raise ValueError(
            f"Event extraction quality validation failed: {'; '.join(issues)}"
        )

    logger.info(
        f"Event extraction final validation passed with {len(events)} events."
    )

    return {
        "event_timeline": event_timeline,
        "final_event_timeline": event_timeline,
        "parsed_settings": parsed_settings,
        "merged_events": events,
    }


def copy_timeline(timeline: dict) -> dict:
    """Safely deepcopy timeline with robust fallback."""
    import copy

    return copy.deepcopy(timeline)
