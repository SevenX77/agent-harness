import logging
from pathlib import Path
from graph_agent.core.runner import run_skill
from graph_agent.core.local_workspace_resolver import LocalWorkspaceResolver

logger = logging.getLogger(__name__)


def extract_all_events(context) -> dict:
    """遍历所有分段结果，调用 event-extraction skill 提取事件。"""
    all_segmentations = context.get("all_segmentations", [])
    all_events = []
    prev_chapter_last_event = None

    repo_root = Path(__file__).resolve().parents[5]
    skills_base = repo_root / "skills"
    workspace_dir = repo_root / ".workspace"
    resolver = LocalWorkspaceResolver(search_paths=[repo_root, skills_base])

    for seg_data in all_segmentations:
        chapter_number = seg_data.get("chapter_number")
        segmentation = seg_data.get("segmentation", {})

        logger.info(f"Extracting events from chapter {chapter_number}")

        result = run_skill(
            skills_base / "event-extraction",
            workspace_dir=workspace_dir,
            skill_resolver=resolver,
            chapter_number=chapter_number,
            segments=segmentation.get("paragraphs", []),
            prev_chapter_last_event=prev_chapter_last_event,
        )

        event_ctx = result.context
        chapter_events = event_ctx.get("event_timeline", {}).get("events", [])

        all_events.append({
            "chapter_number": chapter_number,
            "events": chapter_events,
        })

        if chapter_events:
            prev_chapter_last_event = chapter_events[-1]

    total_events = sum(len(ch.get("events", [])) for ch in all_events)
    total_chapters = len(all_events)

    logger.info(f"Extracted {total_events} events from {total_chapters} chapters")
    return {
        "all_events": all_events,
        "total_events": total_events,
        "total_chapters": total_chapters,
    }
