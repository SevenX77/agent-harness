"""Event extraction tools for story deconstruction."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def format_segments_for_prompt(context: dict) -> str:
    """Format segmented paragraphs as markdown for LLM prompt."""
    segmentation = context.get("segmentation_result", {})
    paragraphs = segmentation.get("paragraphs", [])

    lines = []
    for para in paragraphs:
        para_type = para.get("type", "B")
        type_name = {"A": "A类-设定", "B": "B类-事件", "C": "C类-系统"}.get(para_type, para_type)
        lines.append(f"### 段落 {para.get('index', 0)} [{type_name}]")
        lines.append("")
        lines.append(para.get("content", ""))
        lines.append("")
        lines.append("---")
        lines.append("")

    formatted = "\n".join(lines)
    context["formatted_paragraphs"] = formatted

    logger.info(f"Formatted {len(paragraphs)} paragraphs")
    return f"Formatted {len(paragraphs)} paragraphs"


def parse_events(raw_output: str, context: dict) -> str:
    """Parse event markdown from LLM output with N:1 constraint."""
    events = []
    lines = raw_output.split("\n")
    assigned_paragraphs: set[int] = set()
    current_event = None
    event_index = 0

    for line in lines:
        line = line.strip()
        event_match = re.match(r"^##\s*事件(\d+)[：:](.+?)$", line)
        if event_match:
            if current_event:
                events.append(_build_event_dict(current_event, assigned_paragraphs))
            event_index = int(event_match.group(1))
            current_event = {
                "index": event_index,
                "summary": event_match.group(2).strip(),
                "event_type": None,
                "paragraphs": [],
                "location": "",
                "location_change": None,
                "time": "",
                "time_change": None,
            }
            continue

        if current_event:
            if line.startswith("**类型**"):
                match = re.search(r"([BC])类", line)
                if match:
                    current_event["event_type"] = match.group(1)
            elif line.startswith("**包含段落**"):
                m = re.match(r"\*\*包含段落\*\*[：:]\s*(.*)", line)
                if m:
                    current_event["paragraphs"] = parse_paragraph_indices(
                        m.group(1).strip(), context
                    )
            elif line.startswith("**地点**") and "**地点变化**" not in line:
                m = re.match(r"\*\*地点\*\*[：:]\s*(.*)", line)
                if m:
                    current_event["location"] = m.group(1).strip()
            elif line.startswith("**地点变化**"):
                m = re.match(r"\*\*地点变化\*\*[：:]\s*(.*)", line)
                if m:
                    current_event["location_change"] = m.group(1).strip() or None
            elif line.startswith("**时间**") and "**时间变化**" not in line:
                m = re.match(r"\*\*时间\*\*[：:]\s*(.*)", line)
                if m:
                    current_event["time"] = m.group(1).strip()
            elif line.startswith("**时间变化**"):
                m = re.match(r"\*\*时间变化\*\*[：:]\s*(.*)", line)
                if m:
                    current_event["time_change"] = m.group(1).strip() or None

    if current_event:
        events.append(_build_event_dict(current_event, assigned_paragraphs))

    context["parsed_events"] = events
    logger.info(f"Parsed {len(events)} events")
    return f"Parsed {len(events)} events"


def _build_event_dict(event_dict: dict, assigned_paragraphs: set) -> dict:
    """Build event dict with N:1 constraint enforcement."""
    unique_paragraphs = []
    for para_index in event_dict.get("paragraphs", []):
        if para_index in assigned_paragraphs:
            logger.warning(f"Paragraph {para_index} already assigned")
        else:
            unique_paragraphs.append(para_index)
            assigned_paragraphs.add(para_index)
    event_dict["paragraphs"] = unique_paragraphs
    return event_dict


def parse_paragraph_indices(text: str, context: dict) -> list[int]:
    """Robustly parse paragraph indices from various formats."""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]

    text = re.sub(r"[；;、/|]", ",", text)
    text = text.replace("，", ",")
    text = text.replace("段落", "")
    text = text.replace("第", "")

    tokens = [t.strip() for t in text.split(",") if t.strip()]
    result = []

    for token in tokens:
        range_match = re.match(r"^(\d+)\s*(?:-|~|至|到)\s*(\d+)$", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start <= end:
                result.extend(list(range(start, end + 1)))
            else:
                result.extend(list(range(end, start + 1)))
            continue
        num_match = re.findall(r"\d+", token)
        if num_match:
            result.extend(int(x) for x in num_match)

    seen = set()
    dedup = []
    for idx in result:
        if idx not in seen:
            dedup.append(idx)
            seen.add(idx)
    return dedup


def store_events(context: dict) -> str:
    """Store events as EventEntry list and build event timeline."""
    parsed_events = context.get("parsed_events", [])
    segmentation = context.get("segmentation_result", {})
    chapter_number = segmentation.get("chapter_number", 0)

    event_entries = []
    for event in parsed_events:
        event_idx = event.get("index", 0)
        event_type = event.get("event_type", "B")
        event_id = f"{chapter_number:04d}{event_idx:05d}{event_type}"

        entry = {
            "event_id": event_id,
            "event_summary": event.get("summary", ""),
            "event_type": event_type,
            "paragraph_indices": event.get("paragraphs", []),
            "location": event.get("location", "位置未明确"),
            "location_change": event.get("location_change"),
            "time": event.get("time", "时间未明确"),
            "time_change": event.get("time_change"),
            "setting": [],
            "is_inferred": [],
        }
        event_entries.append(entry)

    context["event_entries"] = event_entries

    event_timeline = {
        "chapter_number": chapter_number,
        "total_events": len(event_entries),
        "events": event_entries,
        "metadata": {"type_distribution": _calculate_type_distribution(event_entries)},
    }
    context["event_timeline"] = event_timeline

    logger.info(f"Stored {len(event_entries)} events")
    return f"Stored {len(event_entries)} events"


def backup_event_timeline(context: dict) -> str:
    """Backup event timeline before review phase."""
    import copy

    event_timeline = context.get("event_timeline", {})
    if event_timeline:
        context["_original_event_timeline"] = copy.deepcopy(event_timeline)
        logger.info(f"Backed up {event_timeline.get('total_events', 0)} events")
        return f"Backed up {event_timeline.get('total_events', 0)} events"
    return "No events to backup"


def safe_review_store_events(context: dict) -> str:
    """Safely store reviewed events with fallback to original data."""
    # Backup original timeline before review
    original_timeline = context.get("_original_event_timeline")

    # Try to store new parsed events
    parsed_events = context.get("parsed_events", [])

    # If parse failed (0 events) and we have original data, restore it
    if len(parsed_events) == 0 and original_timeline:
        context["event_timeline"] = original_timeline
        context["event_entries"] = original_timeline.get("events", [])
        logger.warning("Review parse returned 0 events, restored original timeline")
        return f"Restored {original_timeline.get('total_events', 0)} original events"

    # Otherwise proceed with normal store
    return store_events(context)


def _calculate_type_distribution(events: list[dict]) -> dict[str, int]:
    """Calculate event type distribution."""
    distribution = {"A": 0, "B": 0, "C": 0}
    for event in events:
        event_type = event.get("event_type", "B")
        if event_type in distribution:
            distribution[event_type] += 1
    return distribution


def parse_settings(raw_output: str, context: dict) -> str:
    """Parse setting markdown from LLM output."""
    settings = []
    lines = raw_output.split("\n")
    current_setting = None

    for line in lines:
        line = line.strip()
        setting_match = re.match(r"^##\s*设定(\d+)[：:](.+?)$", line)
        if setting_match:
            if current_setting:
                settings.append(current_setting)
            current_setting = {
                "setting_id": f"S{setting_match.group(1)}",
                "setting_title": setting_match.group(2).strip(),
                "paragraph_index": None,
                "related_event": None,
                "setting_summary": "",
            }
            continue

        if current_setting:
            if line.startswith("**段落**"):
                m = re.search(r"(\d+)", line)
                if m:
                    current_setting["paragraph_index"] = int(m.group(1))
            elif line.startswith("**关联事件**"):
                m = re.search(r"事件(\d+)", line)
                if m:
                    current_setting["related_event"] = int(m.group(1))
            elif line.startswith("**核心知识点**"):
                m = re.match(r"\*\*核心知识点\*\*[：:]\s*(.*)", line)
                if m:
                    current_setting["setting_summary"] = m.group(1).strip()

    if current_setting:
        settings.append(current_setting)

    context["parsed_settings"] = settings
    logger.info(f"Parsed {len(settings)} settings")
    return f"Parsed {len(settings)} settings"


def merge_settings_into_events(context: dict) -> str:
    """Merge settings into events with N:1 constraint."""
    event_timeline = context.get("event_timeline", {})
    events = event_timeline.get("events", [])
    settings = context.get("parsed_settings", [])

    owned = {}
    for idx, ev in enumerate(events):
        for pi in ev.get("paragraph_indices", []):
            owned[pi] = idx

    for st in settings:
        related_event = st.get("related_event")
        if not related_event or related_event < 1 or related_event > len(events):
            continue

        target_idx = related_event - 1
        target = events[target_idx]

        setting_item = {
            "setting_id": st.get("setting_id", ""),
            "setting_title": st.get("setting_title", ""),
            "setting_summary": st.get("setting_summary", ""),
            "paragraph_indices": [st.get("paragraph_index", 0)]
            if st.get("paragraph_index")
            else [],
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

    context["merged_events"] = events
    logger.info(f"Merged {len(settings)} settings")
    return f"Merged {len(settings)} settings"


def finalize_event_timeline(context: dict) -> str:
    """Finalize and assemble the complete EventTimeline dict."""
    event_timeline = context.get("event_timeline", {})
    merged_events = context.get("merged_events", [])

    event_timeline["events"] = merged_events
    event_timeline["total_events"] = len(merged_events)
    event_timeline["metadata"]["type_distribution"] = _calculate_type_distribution(merged_events)

    context["final_event_timeline"] = event_timeline
    logger.info(f"Finalized {len(merged_events)} events")
    return f"Finalized {len(merged_events)} events"


def log_ambiguous_events(event_id: str, reason: str, confidence: float, context: dict) -> str:
    """Log uncertain event extraction decisions for review."""
    if "_ambiguity_reports" not in context:
        context["_ambiguity_reports"] = []

    report = {
        "event_id": event_id,
        "reason": reason,
        "confidence": confidence,
        "layer": "L3_annotation",
    }
    context["_ambiguity_reports"].append(report)

    logger.warning(f"Ambiguous event {event_id}: {reason}")
    return f"Logged ambiguity for event {event_id}"
