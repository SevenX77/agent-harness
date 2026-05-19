"""Event extraction tools for story deconstruction."""
from __future__ import annotations

import logging
import re

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


def format_segments_for_prompt(context: dict) -> str:
    """Format segmented paragraphs as markdown for LLM prompt."""
    segmentation = context.get('segmentation_result', {})
    paragraphs = segmentation.get('paragraphs', [])
    
    lines = []
    for para in paragraphs:
        para_type = para.get('type', 'B')
        type_name = {"A": "A类-设定", "B": "B类-事件", "C": "C类-系统"}.get(para_type, para_type)
        lines.append(f"### 段落 {para.get('index', 0)} [{type_name}]")
        lines.append("")
        lines.append(para.get('content', ''))
        lines.append("")
        lines.append("---")
        lines.append("")
    
    formatted = "\n".join(lines)
    context['formatted_paragraphs'] = formatted
    
    logger.info(f"Formatted {len(paragraphs)} paragraphs")
    return f"Formatted {len(paragraphs)} paragraphs"


def add_event(
    index: int,
    summary: str,
    type: str,
    paragraphs_str: str,
    location: str,
    location_change: str,
    time: str,
    time_change: str,
    present_characters: str = "",
    *,
    context: dict,
) -> str:
    """Add a single event (small-call pattern to avoid Bridge JSON parse errors).

    Call once per event with scalar parameters only. Accumulates into
    context['parsed_events'] for a subsequent store_events() call.

    Args:
        index: Event number (1-based).
        summary: One-line event summary (20-30 chars).
        type: "B" (real-world event), "C" (system/meta-space event), or "M" (memory/flashback outside current timeline).
        paragraphs_str: Paragraph indices as string, e.g. "1, 2, 3" or "1-5".
        location: Location name from original text (原文原词), or "位置未明确".
        location_change: Change vs previous event, or "" if none.
        time: Time descriptor from original text (原文原词), or "时间未明确".
        time_change: Change vs previous event, or "" if none.
        present_characters: Comma-separated list of characters present, e.g. "姜宁, 张超".
        context: Injected by framework.
    """
    if "parsed_events" not in context:
        context["parsed_events"] = []

    para_indices = parse_paragraph_indices(paragraphs_str, context)

    event_dict = {
        "index": index,
        "summary": summary,
        "event_type": type,
        "paragraphs": para_indices,
        "location": location or "位置未明确",
        "location_change": location_change if location_change else None,
        "time": time or "时间未明确",
        "time_change": time_change if time_change else None,
        "present_characters": [c.strip() for c in present_characters.split(",") if c.strip()],
    }

    # Deduplicate by index: keep last (review pass may overwrite aggregate events)
    context["parsed_events"] = [
        e for e in context["parsed_events"] if e["index"] != index
    ]
    context["parsed_events"].append(event_dict)

    logger.info("Added event %d (%s): %s...", index, type, summary[:30])
    return f"Added event {index} ({type}): paragraphs={para_indices}"


def parse_events(raw_output: str, context: dict) -> str:
    """Parse event markdown from LLM output with N:1 constraint (legacy; prefer add_event)."""
    events = []
    lines = raw_output.split("\n")
    assigned_paragraphs: set[int] = set()
    current_event = None
    event_index = 0
    
    for line in lines:
        line = line.strip()
        event_match = re.match(r'^##\s*事件(\d+)[：:](.+?)$', line)
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
                match = re.search(r'([BC])类', line)
                if match:
                    current_event["event_type"] = match.group(1)
            elif line.startswith("**包含段落**"):
                m = re.match(r'\*\*包含段落\*\*[：:]\s*(.*)', line)
                if m:
                    current_event["paragraphs"] = parse_paragraph_indices(m.group(1).strip(), context)
            elif line.startswith("**地点**") and "**地点变化**" not in line:
                m = re.match(r'\*\*地点\*\*[：:]\s*(.*)', line)
                if m:
                    current_event["location"] = m.group(1).strip()
            elif line.startswith("**地点变化**"):
                m = re.match(r'\*\*地点变化\*\*[：:]\s*(.*)', line)
                if m:
                    current_event["location_change"] = m.group(1).strip() or None
            elif line.startswith("**时间**") and "**时间变化**" not in line:
                m = re.match(r'\*\*时间\*\*[：:]\s*(.*)', line)
                if m:
                    current_event["time"] = m.group(1).strip()
            elif line.startswith("**时间变化**"):
                m = re.match(r'\*\*时间变化\*\*[：:]\s*(.*)', line)
                if m:
                    current_event["time_change"] = m.group(1).strip() or None
    
    if current_event:
        events.append(_build_event_dict(current_event, assigned_paragraphs))
    
    context['parsed_events'] = events
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
    """Store events as EventEntry list and build event timeline.

    Sorts parsed_events by index, applies N:1 paragraph assignment enforcement,
    and writes to context['event_timeline'].

    M-type events (memory/flashback) are stored in both event_timeline.events
    (for entity registration in downstream batch-analysis) and separately in
    context['memory_events'] (for revenge-debt / narrative-promise tracking).
    M-type events are excluded from the main narrative timeline ordering —
    they retain their index but are tagged is_memory=True.
    """
    raw_parsed = context.get('parsed_events', [])
    # Sort by index (add_event may append out-of-order during review)
    parsed_events = sorted(raw_parsed, key=lambda e: e.get('index', 0))

    segmentation = context.get('segmentation_result', {})
    chapter_number = segmentation.get('chapter_number', 0)

    assigned: set[int] = set()
    event_entries = []
    memory_entries = []
    for event in parsed_events:
        event_idx = event.get('index', 0)
        event_type = event.get('event_type', 'B')
        event_id = f"{chapter_number:04d}{event_idx:05d}{event_type}"

        # N:1 enforcement: each paragraph only belongs to one event
        para_indices = []
        for pi in event.get('paragraphs', []):
            if pi in assigned:
                logger.warning(
                    "Paragraph %d already assigned; skipping in event %d", pi, event_idx
                )
            else:
                para_indices.append(pi)
                assigned.add(pi)

        entry = {
            "event_id": event_id,
            "event_summary": event.get('summary', ''),
            "event_type": event_type,
            "paragraph_indices": para_indices,
            "location": event.get('location', '位置未明确'),
            "location_change": event.get('location_change'),
            "time": event.get('time', '时间未明确'),
            "time_change": event.get('time_change'),
            "present_characters": event.get('present_characters', []),
            "setting": [],
            "is_inferred": [],
            "is_memory": event_type == "M",
        }
        event_entries.append(entry)
        if event_type == "M":
            memory_entries.append(entry)

    context['event_entries'] = event_entries
    context['memory_events'] = memory_entries

    event_timeline = {
        "chapter_number": chapter_number,
        "total_events": len(event_entries),
        "events": event_entries,
        "metadata": {
            "type_distribution": _calculate_type_distribution(event_entries),
            "memory_event_count": len(memory_entries),
        }
    }
    context['event_timeline'] = event_timeline

    logger.info(
        "Stored %d events (%d memory/flashback)", len(event_entries), len(memory_entries)
    )
    return f"Stored {len(event_entries)} events ({len(memory_entries)} memory/flashback)"


def backup_event_timeline(context: dict) -> str:
    """Backup event timeline before review phase."""
    import copy
    event_timeline = context.get('event_timeline', {})
    if event_timeline:
        context['_original_event_timeline'] = copy.deepcopy(event_timeline)
        logger.info(f"Backed up {event_timeline.get('total_events', 0)} events")
        return f"Backed up {event_timeline.get('total_events', 0)} events"
    return "No events to backup"


def safe_review_store_events(context: dict) -> str:
    """Safely store reviewed events with fallback to original data."""
    # Backup original timeline before review
    original_timeline = context.get('_original_event_timeline')

    # Try to store new parsed events
    parsed_events = context.get('parsed_events', [])

    # If parse failed (0 events) and we have original data, restore it
    if len(parsed_events) == 0 and original_timeline:
        context['event_timeline'] = original_timeline
        context['event_entries'] = original_timeline.get('events', [])
        logger.warning("Review parse returned 0 events, restored original timeline")
        return f"Restored {original_timeline.get('total_events', 0)} original events"

    # Otherwise proceed with normal store
    return store_events(context)


def _calculate_type_distribution(events: list[dict]) -> dict[str, int]:
    """Calculate event type distribution."""
    distribution = {"A": 0, "B": 0, "C": 0, "M": 0}
    for event in events:
        event_type = event.get('event_type', 'B')
        if event_type in distribution:
            distribution[event_type] += 1
    return distribution


def parse_settings(raw_output: str, context: dict) -> str:
    """Parse setting markdown from LLM output using md_to_json."""
    setting_items = md_to_json(raw_output, Setting) if raw_output.strip() else []
    settings = [item.model_dump() for item in setting_items]
    context["parsed_settings"] = settings
    logger.info("Parsed %d settings", len(settings))
    return f"Parsed {len(settings)} settings"


def merge_settings_into_events(context: dict) -> str:
    """Merge settings into events with N:1 constraint."""
    event_timeline = context.get('event_timeline', {})
    events = event_timeline.get('events', [])
    settings = context.get('parsed_settings', [])
    
    owned = {}
    for idx, ev in enumerate(events):
        for pi in ev.get('paragraph_indices', []):
            owned[pi] = idx
    
    for st in settings:
        related_event = st.get("related_event")
        if not related_event or related_event < 1 or related_event > len(events):
            continue
        
        target_idx = related_event - 1
        target = events[target_idx]
        
        setting_item = {
            "setting_id": st.get('setting_id', ''),
            "setting_title": st.get('setting_title', ''),
            "setting_summary": st.get('setting_summary', ''),
            "paragraph_indices": [st.get('paragraph_index', 0)] if st.get('paragraph_index') else []
        }
        
        if 'setting' not in target:
            target['setting'] = []
        target['setting'].append(setting_item)
        
        para_idx = st.get('paragraph_index', 0)
        if para_idx:
            if para_idx in owned and owned[para_idx] != target_idx:
                logger.warning(f"Setting paragraph {para_idx} already owned")
                continue
            if para_idx not in target.get('paragraph_indices', []):
                target['paragraph_indices'].append(para_idx)
                owned[para_idx] = target_idx
        
        target['paragraph_indices'] = sorted(target['paragraph_indices'])
    
    context['merged_events'] = events
    logger.info(f"Merged {len(settings)} settings")
    return f"Merged {len(settings)} settings"


def finalize_event_timeline(context: dict) -> str:
    """Finalize and assemble the complete EventTimeline dict."""
    event_timeline = context.get('event_timeline', {})
    merged_events = context.get('merged_events', [])
    
    event_timeline['events'] = merged_events
    event_timeline['total_events'] = len(merged_events)
    event_timeline['metadata']['type_distribution'] = _calculate_type_distribution(merged_events)
    
    context['final_event_timeline'] = event_timeline
    logger.info(f"Finalized {len(merged_events)} events")
    return f"Finalized {len(merged_events)} events"


def log_ambiguous_events(event_id: str, reason: str, confidence: float, context: dict) -> str:
    """Log uncertain event extraction decisions for review."""
    if '_ambiguity_reports' not in context:
        context['_ambiguity_reports'] = []
    
    report = {
        "event_id": event_id,
        "reason": reason,
        "confidence": confidence,
        "layer": "L3_annotation"
    }
    context['_ambiguity_reports'].append(report)
    
    logger.warning(f"Ambiguous event {event_id}: {reason}")
    return f"Logged ambiguity for event {event_id}"
