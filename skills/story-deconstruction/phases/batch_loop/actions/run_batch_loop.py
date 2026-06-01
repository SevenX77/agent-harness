import logging
from pathlib import Path
from graph_agent.core.runner import run_skill
from graph_agent.core.local_workspace_resolver import LocalWorkspaceResolver

logger = logging.getLogger(__name__)


def run_batch_loop(context) -> dict:
    """执行批次分析循环。"""
    all_events = context.get("all_events", [])

    # 1. 发现追踪维度
    dynamic_dimensions = ["plot_progression", "character_development", "tension_level"]

    # 2. 扁平化所有事件
    flat_events = []
    for ch in all_events:
        ch_num = ch.get("chapter_number")
        for event in ch.get("events", []):
            flat_events.append({
                **event,
                "chapter_number": ch_num,
            })

    # 3. 循环批次处理
    batch_size = 10
    total_batches = (len(flat_events) + batch_size - 1) // batch_size
    all_batch_results = []
    accumulated_context = {}

    repo_root = Path(__file__).resolve().parents[5]
    skills_base = repo_root / "skills"
    workspace_dir = repo_root / ".workspace"
    resolver = LocalWorkspaceResolver(search_paths=[repo_root, skills_base])

    for batch_index in range(total_batches):
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

        logger.info(f"Running batch analysis for Batch {batch_index + 1}: chapters {chapter_range}")

        # 调用 batch-analysis 技能
        result = run_skill(
            skills_base / "batch-analysis",
            workspace_dir=workspace_dir,
            skill_resolver=resolver,
            batch_events=batch_events,
            accumulated_context=accumulated_context,
            dynamic_dimensions=dynamic_dimensions,
            chapter_range=chapter_range,
        )

        batch_ctx = result.context
        batch_result = batch_ctx.get("batch_result", {})
        updated_accumulated = batch_ctx.get("updated_accumulated", {})

        all_batch_results.append({
            "batch_index": batch_index + 1,
            "chapter_range": chapter_range,
            "result": batch_result,
        })
        accumulated_context = updated_accumulated

    logger.info(f"Batch analysis completed: {len(all_batch_results)} batches")
    return {
        "batch_outputs": all_batch_results,
        "accumulated_context": accumulated_context,
        "entity_registry": accumulated_context.get("entity_registry", {}),
    }
