import logging
from pathlib import Path
from graph_agent.core.runner import run_skill
from graph_agent.core.local_workspace_resolver import LocalWorkspaceResolver

logger = logging.getLogger(__name__)


def segment_all_chapters(context) -> dict:
    """遍历所有章节，调用 text-segmentation skill 进行分段。"""
    chapters = context.get("chapters", [])
    all_segmentations = []

    repo_root = Path(__file__).resolve().parents[5]
    skills_base = repo_root / "skills"
    workspace_dir = repo_root / ".workspace"
    resolver = LocalWorkspaceResolver(search_paths=[repo_root, skills_base])

    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        content = chapter.get("content", "")

        logger.info(f"Segmenting chapter {chapter_number}")

        result = run_skill(
            skills_base / "text-segmentation",
            workspace_dir=workspace_dir,
            skill_resolver=resolver,
            chapter_number=chapter_number,
            chapter_content=content,
        )

        segmentation_ctx = result.context
        segmentation_result = segmentation_ctx.get("segmentation_result", {})

        all_segmentations.append({
            "chapter_number": chapter_number,
            "segmentation": segmentation_result,
        })

    logger.info(f"Segmented {len(chapters)} chapters into {len(all_segmentations)} segmentations")
    return {"all_segmentations": all_segmentations}
