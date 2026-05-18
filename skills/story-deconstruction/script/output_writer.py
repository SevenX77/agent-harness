from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from story_forge.core.data_manager import DataManager

logger = logging.getLogger(__name__)


def write_outputs(context: dict, data_manager: DataManager) -> None:
    """Convert orchestrator context into standardized JSON + MD outputs.

    Writes four files to data_manager.output_dir:
    - chapters_events.json  (code consumption — filtering, indexing)
    - chapters_events.md    (LLM consumption — direct prompt injection)
    - global_analysis.json  (code consumption)
    - global_analysis.md    (LLM consumption)
    """
    all_events = context.get("all_events", [])
    all_batch_results = context.get("all_batch_results", [])
    accumulated_context = context.get("accumulated_context", {})
    story_framework = context.get("story_framework", {})

    chapters_events = _build_chapters_events(all_events, all_batch_results)
    global_analysis = _build_global_analysis(
        accumulated_context, all_events, all_batch_results, story_framework
    )

    out_dir = data_manager.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    _atomic_write_json(out_dir / "chapters_events.json", chapters_events)
    _atomic_write_text(out_dir / "chapters_events.md", _render_chapters_events_md(chapters_events))
    _atomic_write_json(out_dir / "global_analysis.json", global_analysis)
    _atomic_write_text(out_dir / "global_analysis.md", _render_global_analysis_md(global_analysis))

    logger.info(
        "Output written: %d chapters, %d total events -> %s",
        len(chapters_events),
        sum(len(ch.get("events", [])) for ch in chapters_events),
        out_dir,
    )


# ── JSON builders ──


def _build_chapters_events(
    all_events: list[dict],
    all_batch_results: list[dict],
) -> list[dict]:
    """Build chapters_events.json structure from orchestrator data."""
    tension_index = _build_tension_index(all_batch_results)
    merged_index = _build_merged_events_index(all_batch_results)

    chapters = []
    for ch_data in all_events:
        ch_num = ch_data.get("chapter_number", 0)
        events = []
        for ev in ch_data.get("events", []):
            event_id = ev.get("event_id", "")
            tension = tension_index.get(event_id, {})
            merged = merged_index.get(event_id, {})

            events.append({
                "event_id": event_id,
                "event_summary": ev.get("event_summary", ""),
                "summary": ev.get("event_summary", ""),
                "event_type": ev.get("event_type", "B"),
                "location": ev.get("location", ""),
                "time": ev.get("time", ""),
                "paragraph_indices": ev.get("paragraph_indices", []),
                "emotional_intensity": max(0, min(10, tension.get("emotion_intensity", 0))),
                "climax_intensity": max(0, min(10, tension.get("climax_intensity", 0))),
                "characters": ev.get("present_characters", ev.get("characters", [])),
                "settings": ev.get("settings", ev.get("setting", [])),
                "prop_changes": merged.get("prop_changes", {}),
                "emotional_arc": merged.get("emotional_arc", {}),
                "foreshadowing": merged.get("foreshadowing", {}),
                "spatiotemporal": merged.get("spatiotemporal", {}),
                "system_evolution": merged.get("system_evolution", {}),
            })

        chapters.append({
            "chapter_index": ch_num,
            "events": events,
        })

    return chapters


def _build_global_analysis(
    accumulated_context: dict,
    all_events: list[dict],
    all_batch_results: list[dict],
    story_framework: dict | None = None,
) -> dict:
    """Build global_analysis.json structure from accumulated context and story_framework."""
    known_characters = accumulated_context.get("known_characters", {})
    known_props = accumulated_context.get("known_props", {})

    # LLM may return a list instead of a dict — normalize to dict
    if isinstance(known_characters, list):
        known_characters = {
            (item.get("name", str(i)) if isinstance(item, dict) else str(item)): item
            for i, item in enumerate(known_characters)
        }
    if isinstance(known_props, list):
        known_props = {
            (item.get("name", str(i)) if isinstance(item, dict) else str(item)): item
            for i, item in enumerate(known_props)
        }

    character_arcs = []
    for name, info in known_characters.items():
        if isinstance(info, dict):
            character_arcs.append({
                "name": name,
                "role": info.get("role", "其他"),
                "arc_summary": info.get("current_state", ""),
            })
        else:
            character_arcs.append({
                "name": name,
                "role": "其他",
                "arc_summary": str(info),
            })

    tension_index = _build_tension_index(all_batch_results)
    emotional_arc = _build_emotional_arc(all_events, tension_index)

    all_settings: list[dict] = []
    seen_titles: set[str] = set()
    for ch_data in all_events:
        for ev in ch_data.get("events", []):
            for setting in ev.get("settings", []):
                title = setting.get("setting_title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    all_settings.append({
                        "content": title,
                        "category": "场景",
                    })

    story_skeleton = _build_story_skeleton(all_events, tension_index)

    sf = story_framework or {}
    return {
        "themes": sf.get("themes", []),
        "character_arcs": character_arcs,
        "character_ranking": sf.get("character_ranking", []),
        "emotional_arc": emotional_arc,
        "character_visual_notes": sf.get("entity_registry", {}),
        "settings_registry": all_settings,
        "story_skeleton": story_skeleton,
        "climax_ranking": sf.get("climax_ranking", []),
        "foreshadowing_closure": sf.get("foreshadowing_closure", []),
        "unified_event_stream": sf.get("unified_event_stream", []),
        "scenes": sf.get("scenes", []),
        "known_characters": known_characters,
        "known_props": known_props,
    }


# ── MD renderers ──


def _render_chapters_events_md(chapters_events: list[dict]) -> str:
    """Render chapters_events data as structured Markdown for LLM consumption."""
    lines: list[str] = []
    lines.append("# Story Deconstruction — Chapter Events")
    lines.append("")

    total_events = sum(len(ch.get("events", [])) for ch in chapters_events)
    lines.append(f"Total: {len(chapters_events)} chapters, {total_events} events")
    lines.append("")

    for ch in chapters_events:
        ch_idx = ch.get("chapter_index", 0)
        events = ch.get("events", [])
        lines.append(f"## Chapter {ch_idx} ({len(events)} events)")
        lines.append("")

        for ev in events:
            eid = ev.get("event_id", "?")
            summary = ev.get("event_summary", "")
            location = ev.get("location", "?")
            time = ev.get("time", "?")
            emo = ev.get("emotional_intensity", 0)
            climax = ev.get("climax_intensity", 0)
            etype = ev.get("event_type", "?")

            lines.append(f"### [{eid}] {summary}")
            lines.append(f"- Type: {etype} | Location: {location} | Time: {time}")
            lines.append(f"- Emotional: {emo}/10 | Climax: {climax}/10")

            chars = ev.get("characters", [])
            if chars:
                char_names = ", ".join(
                    c.get("name", "?") if isinstance(c, dict) else str(c)
                    for c in chars
                )
                lines.append(f"- Characters: {char_names}")

            settings = ev.get("settings", [])
            if settings:
                setting_titles = ", ".join(
                    s.get("setting_title", "?") if isinstance(s, dict) else str(s)
                    for s in settings
                )
                lines.append(f"- Settings: {setting_titles}")

            lines.append("")

    return "\n".join(lines)


def _render_global_analysis_md(global_analysis: dict) -> str:
    """Render global_analysis data as structured Markdown for LLM consumption."""
    lines: list[str] = []
    lines.append("# Story Deconstruction — Global Analysis")
    lines.append("")

    # Character arcs
    arcs = global_analysis.get("character_arcs", [])
    lines.append(f"## Characters ({len(arcs)})")
    lines.append("")
    for arc in arcs:
        name = arc.get("name", "?")
        role = arc.get("role", "?")
        summary = arc.get("arc_summary", "")
        lines.append(f"- **{name}** ({role}): {summary}")
    lines.append("")

    # Emotional arc
    emotional_arc = global_analysis.get("emotional_arc", [])
    if emotional_arc:
        lines.append("## Emotional Arc (by chapter)")
        lines.append("")
        for entry in emotional_arc:
            ch = entry.get("chapter_index", "?")
            avg = entry.get("average_climax_intensity", 0)
            lines.append(f"- Chapter {ch}: avg climax {avg:.1f}/10")
        lines.append("")

    # Settings
    settings = global_analysis.get("settings_registry", [])
    if settings:
        lines.append(f"## Settings Registry ({len(settings)})")
        lines.append("")
        for s in settings:
            content = s.get("content", "?")
            category = s.get("category", "?")
            lines.append(f"- {content} ({category})")
        lines.append("")

    # Story skeleton
    skeleton = global_analysis.get("story_skeleton", [])
    if skeleton:
        lines.append(f"## Story Skeleton (top {len(skeleton)} climax events)")
        lines.append("")
        for i, s in enumerate(skeleton, 1):
            lines.append(f"{i}. {s}")
        lines.append("")

    # Known props
    props = global_analysis.get("known_props", {})
    if props:
        lines.append(f"## Known Props ({len(props)})")
        lines.append("")
        for name, info in props.items():
            if isinstance(info, dict):
                lines.append(f"- **{name}**: {info.get('current_state', '')}")
            else:
                lines.append(f"- **{name}**: {info}")
        lines.append("")

    return "\n".join(lines)


# ── Helpers ──


def _build_tension_index(all_batch_results: list[dict]) -> dict[str, dict]:
    """Build event_id → tension data mapping from batch results."""
    index: dict[str, dict] = {}
    for batch in all_batch_results:
        result = batch.get("result", [])
        if not isinstance(result, list):
            logger.warning("batch result is not a list (type=%s), skipping", type(result).__name__)
            continue
        for ev in result:
            eid = ev.get("event_id", "")
            tension = ev.get("tension", {})
            if eid:
                index[eid] = tension
    return index


def _build_merged_events_index(all_batch_results: list[dict]) -> dict[str, dict]:
    """Build event_id → merged event data mapping from batch results."""
    index: dict[str, dict] = {}
    for batch in all_batch_results:
        result = batch.get("result", [])
        if not isinstance(result, list):
            continue
        for ev in result:
            eid = ev.get("event_id", "")
            if eid:
                index[eid] = ev
    return index


def _build_emotional_arc(
    all_events: list[dict],
    tension_index: dict[str, dict],
) -> list[dict]:
    """Build per-chapter emotional arc from tension data."""
    arc = []
    for ch_data in all_events:
        ch_num = ch_data.get("chapter_number", 0)
        intensities = []
        for ev in ch_data.get("events", []):
            eid = ev.get("event_id", "")
            tension = tension_index.get(eid, {})
            climax = tension.get("climax_intensity", 0)
            intensities.append(climax)

        avg = sum(intensities) / len(intensities) if intensities else 0
        arc.append({
            "chapter_index": ch_num,
            "average_climax_intensity": round(avg, 2),
        })
    return arc


def _build_story_skeleton(
    all_events: list[dict],
    tension_index: dict[str, dict],
    top_n: int = 20,
) -> list[str]:
    """Extract top N highest-climax event summaries."""
    scored: list[tuple[float, str]] = []
    for ch_data in all_events:
        for ev in ch_data.get("events", []):
            eid = ev.get("event_id", "")
            tension = tension_index.get(eid, {})
            climax = tension.get("climax_intensity", 0)
            summary = ev.get("event_summary", "")
            if summary:
                scored.append((climax, summary))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:top_n]]


def _atomic_write_json(path: Path, data: object) -> None:
    """Write JSON atomically: temp file + rename."""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically: temp file + rename."""
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
