from __future__ import annotations

import copy
import logging
import re

logger = logging.getLogger(__name__)


def parse_paragraph_indices(text: str) -> list[int]:
    """Robustly parse paragraph indices from various formats."""
    text = str(text).strip()
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


def _calculate_type_distribution(events: list[dict]) -> dict[str, int]:
    distribution = {"A": 0, "B": 0, "C": 0, "M": 0}
    for event in events:
        event_type = event.get("event_type", "B")
        if event_type in distribution:
            distribution[event_type] += 1
    return distribution


def format_events_raw(event_entries: list[dict]) -> str:
    """Format events as markdown text for subsequent stages."""
    lines = []
    for ev in event_entries:
        index = ev.get("event_id", "")[-5:]
        try:
            index = int(index[:-1])
        except ValueError:
            index = ev.get("event_id", "?")
        
        lines.append(f"## 事件{index}：{ev.get('summary', '')}")
        lines.append(f"**类型**：{ev.get('event_type', 'B')}类")
        paras = ", ".join(map(str, ev.get("paragraph_indices", [])))
        lines.append(f"**包含段落**：{paras}")
        lines.append(f"**地点**：{ev.get('location', '位置未明确')}")
        if ev.get("location_change"):
            lines.append(f"**地点变化**：{ev.get('location_change')}")
        lines.append(f"**时间**：{ev.get('time', '时间未明确')}")
        if ev.get("time_change"):
            lines.append(f"**时间变化**：{ev.get('time_change')}")
        if ev.get("present_characters"):
            lines.append(f"**在场角色**：{', '.join(ev.get('present_characters'))}")
        lines.append("")
    return "\n".join(lines)


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate and process event aggregation from LLM finish output."""
    raw_events = output.get("parsed_events") or output.get("events") or []
    if not raw_events:
        raise ValueError("No events produced by aggregate phase")

    chapter_number = state_slice.get("chapter_number", 0)

    # 1. Map raw events to context format
    parsed_events = []
    for e in raw_events:
        index = int(e.get("index", 0))
        summary = e.get("summary", "")
        etype = e.get("type") or e.get("event_type") or "B"
        paragraphs_str = str(e.get("paragraphs_str") or e.get("paragraphs") or "")
        para_indices = parse_paragraph_indices(paragraphs_str)

        location = e.get("location") or "位置未明确"
        location_change = e.get("location_change") or None
        time = e.get("time") or "时间未明确"
        time_change = e.get("time_change") or None

        characters_str = str(e.get("present_characters") or "")
        present_characters = [
            c.strip() for c in characters_str.split(",") if c.strip()
        ]

        event_dict = {
            "index": index,
            "summary": summary,
            "event_type": etype,
            "paragraphs": para_indices,
            "location": location,
            "location_change": location_change,
            "time": time,
            "time_change": time_change,
            "present_characters": present_characters,
        }
        parsed_events.append(event_dict)

    # Sort by index
    parsed_events = sorted(parsed_events, key=lambda x: x.get("index", 0))

    # 2. store_events logic with N:1 paragraph assignment
    assigned: set[int] = set()
    event_entries = []
    memory_entries = []

    for event in parsed_events:
        event_idx = event.get("index", 0)
        event_type = event.get("event_type", "B")
        event_id = f"{chapter_number:04d}{event_idx:05d}{event_type}"

        para_indices = []
        for pi in event.get("paragraphs", []):
            if pi in assigned:
                logger.warning(
                    "Paragraph %d already assigned; skipping in event %d", pi, event_idx
                )
            else:
                para_indices.append(pi)
                assigned.add(pi)

        entry = {
            "event_id": event_id,
            "title": event.get("summary", ""),  # Align with timeline schema
            "summary": event.get("summary", ""),
            "type": event_type,  # Align with timeline schema
            "event_type": event_type,
            "paragraph_indices": para_indices,
            "location": event.get("location", "位置未明确"),
            "location_change": event.get("location_change"),
            "time": event.get("time", "时间未明确"),
            "time_change": event.get("time_change"),
            "present_characters": event.get("present_characters", []),
            "setting": [],
            "is_inferred": [],
            "is_memory": event_type == "M",
        }
        event_entries.append(entry)
        if event_type == "M":
            memory_entries.append(entry)

    event_timeline = {
        "chapter_number": chapter_number,
        "total_events": len(event_entries),
        "events": event_entries,
        "settings": [],
        "metadata": {
            "type_distribution": _calculate_type_distribution(event_entries),
            "memory_event_count": len(memory_entries),
        },
    }

    # Backup original timeline before review
    _original_event_timeline = copy.deepcopy(event_timeline)

    # Generate events_raw for the next stage
    events_raw = format_events_raw(event_entries)

    return {
        "parsed_events": parsed_events,
        "event_entries": event_entries,
        "memory_events": memory_entries,
        "event_timeline": event_timeline,
        "_original_event_timeline": _original_event_timeline,
        "events_raw": events_raw,
    }
