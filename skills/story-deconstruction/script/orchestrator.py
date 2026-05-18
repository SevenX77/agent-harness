from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT_PATH = Path(__file__).resolve().parents[3]
SKILLS_BASE_PATH = ROOT_PATH / "skills"


def segment_all_chapters(context: dict) -> str:
    """遍历所有章节，调用 text-segmentation skill 进行分段。"""
    from story_forge.core.graph_agent import run_skill

    chapters = context.get("chapters", [])
    all_segmentations = []

    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        content = chapter.get("content", "")

        logger.info(f"Segmenting chapter {chapter_number}")

        result = run_skill(
            SKILLS_BASE_PATH / "text-segmentation" / "SKILL.md",
            chapter_number=chapter_number,
            chapter_content=content,
        )

        segmentation_ctx = result.get("context", {})
        segmentation_result = segmentation_ctx.get("segmentation_result", {})

        all_segmentations.append({
            "chapter_number": chapter_number,
            "segmentation": segmentation_result,
        })

    context["all_segmentations"] = all_segmentations

    return f"Segmented {len(chapters)} chapters into {len(all_segmentations)} segmentations"


def extract_all_events(context: dict) -> str:
    """遍历所有分段结果，调用 event-extraction skill 提取事件。"""
    from story_forge.core.graph_agent import run_skill

    all_segmentations = context.get("all_segmentations", [])
    all_events = []
    para_text_lookup = {}
    prev_chapter_last_event = None

    for seg_data in all_segmentations:
        chapter_number = seg_data.get("chapter_number")
        segmentation = seg_data.get("segmentation", {})

        logger.info(f"Extracting events from chapter {chapter_number}")

        result = run_skill(
            SKILLS_BASE_PATH / "event-extraction" / "SKILL.md",
            chapter_number=chapter_number,
            segmentation_result=segmentation,
            prev_chapter_last_event=prev_chapter_last_event,
            output_dir=context.get("output_dir", ""),
        )

        event_ctx = result.get("context", {})
        event_timeline = event_ctx.get("event_timeline", {})
        chapter_events = event_timeline.get("events", [])
        para_lookup = event_ctx.get("para_text_lookup", {})

        all_events.append({
            "chapter_number": chapter_number,
            "events": chapter_events,
        })

        para_text_lookup.update(para_lookup)

        if chapter_events:
            prev_chapter_last_event = chapter_events[-1]

    context["all_events"] = all_events
    context["para_text_lookup"] = para_text_lookup
    context["total_events"] = sum(len(ch.get("events", [])) for ch in all_events)
    context["total_chapters"] = len(all_events)

    return (
        f"Extracted {context['total_events']} events "
        f"from {context['total_chapters']} chapters"
    )


def discover_tracking_dimensions(context: dict) -> str:
    """分析前30个事件，通过 LLM 发现需要追踪的动态维度。"""
    all_events = context.get("all_events", [])

    event_summaries = []
    for ch in all_events:
        for event in ch.get("events", []):
            summary = event.get("event_summary") or event.get("description", "")
            if summary:
                event_summaries.append(summary)
            if len(event_summaries) >= 30:
                break
        if len(event_summaries) >= 30:
            break

    logger.info(f"Analyzing {len(event_summaries)} events for dynamic dimensions")

    llm_call = context.get("_llm_call")
    if llm_call and event_summaries:
        prompt = (
            "Based on the following event summaries from a story, "
            "identify key dynamic dimensions that should be tracked "
            "across the narrative:\n\n" +
            "\n".join(f"- {s}" for s in event_summaries) +
            "\n\nReturn a list of dimension names (e.g., 'plot_progression', "
            "'character_development', 'tension_level')."
        )
        response = llm_call(prompt)
        dimensions = [d.strip() for d in response.split("\n") if d.strip()]
    else:
        dimensions = ["plot_progression", "character_development", "tension_level"]

    context["dynamic_dimensions"] = dimensions

    return f"Discovered tracking dimensions: {', '.join(dimensions)}"


def prepare_next_batch(context: dict) -> str:
    """准备下一批事件用于分析。"""
    batch_size = 10
    batch_index = context.get("current_batch_index", 0)
    all_events = context.get("all_events", [])

    flat_events = []
    for ch in all_events:
        ch_num = ch.get("chapter_number")
        for event in ch.get("events", []):
            flat_events.append({
                **event,
                "chapter_number": ch_num,
            })

    start_idx = batch_index * batch_size
    end_idx = start_idx + batch_size
    batch_events = flat_events[start_idx:end_idx]

    batch_chapters = sorted(set(e.get("chapter_number") for e in batch_events))

    if batch_events:
        if batch_chapters[0] == batch_chapters[-1]:
            chapter_range = str(batch_chapters[0])
        else:
            chapter_range = f"{batch_chapters[0]}-{batch_chapters[-1]}"
    else:
        chapter_range = "none"

    context["current_batch_events"] = batch_events
    context["current_chapter_range"] = chapter_range
    context["current_batch_index"] = batch_index + 1

    return f"Batch {batch_index + 1}: chapters {chapter_range}"


def run_batch_analysis(context: dict) -> str:
    """调用 batch-analysis skill 分析当前批次事件。"""
    from story_forge.core.graph_agent import run_skill

    batch_events = context.get("current_batch_events", [])

    logger.info(f"Running batch analysis for {len(batch_events)} events")

    result = run_skill(
        SKILLS_BASE_PATH / "batch-analysis" / "SKILL.md",
        batch_events=batch_events,
        accumulated_context=context.get("accumulated_context", {}),
        para_text_lookup=context.get("para_text_lookup", {}),
        dynamic_dimensions=context.get("dynamic_dimensions", []),
        chapter_range=context.get("current_chapter_range", ""),
    )

    batch_ctx = result.get("context", {})
    batch_result = batch_ctx.get("batch_result", {})
    updated_accumulated = batch_ctx.get("updated_accumulated", {})

    all_batch_results = context.get("all_batch_results", [])
    all_batch_results.append({
        "batch_index": context.get("current_batch_index", 1),
        "chapter_range": context.get("current_chapter_range", ""),
        "result": batch_result,
    })
    context["all_batch_results"] = all_batch_results
    context["accumulated_context"] = updated_accumulated

    return f"Batch analysis complete. Total batches: {len(all_batch_results)}"


def run_global_synthesis(context: dict) -> str:
    """调用 global-synthesis skill 进行全局综合分析。"""
    from story_forge.core.graph_agent import run_skill

    all_batch_results = context.get("all_batch_results", [])
    accumulated_context = context.get("accumulated_context", {})
    entity_registry = context.get("entity_registry", {})

    logger.info(
        "Running global synthesis: %d batches, entity_registry keys=%d",
        len(all_batch_results),
        len(entity_registry),
    )

    result = run_skill(
        SKILLS_BASE_PATH / "global-synthesis" / "SKILL.md",
        batch_outputs=all_batch_results,
        accumulated_context=accumulated_context,
        entity_registry=entity_registry,
    )

    synthesis_ctx = result.get("context", {})
    story_framework = synthesis_ctx.get("story_framework", {})

    context["story_framework"] = story_framework

    climax_count = len(story_framework.get("climax_ranking", []))
    character_count = len(story_framework.get("character_ranking", []))
    scenes_count = len(story_framework.get("scenes", []))

    logger.info(
        "Global synthesis complete: climaxes=%d characters=%d scenes=%d",
        climax_count,
        character_count,
        scenes_count,
    )
    return (
        f"Global synthesis complete: {climax_count} climaxes, "
        f"{character_count} characters, {scenes_count} scenes"
    )


def check_all_batches_done(context: dict) -> str:
    """检查是否所有批次都已处理完成。"""
    batch_size = 10
    all_events = context.get("all_events", [])

    total_events = sum(len(ch.get("events", [])) for ch in all_events)
    total_batches = (total_events + batch_size - 1) // batch_size

    current_batch_index = context.get("current_batch_index", 0)
    processed_batches = current_batch_index

    if processed_batches >= total_batches:
        return "ALL_BATCHES_COMPLETE"

    remaining = total_batches - processed_batches
    return f"BATCHES_REMAINING: {remaining}"
