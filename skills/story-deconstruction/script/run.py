from __future__ import annotations

import json
import logging
import time

from story_forge.core.config import ModelTier
from story_forge.core.data_manager import DataManager

from .orchestrator import (
    check_all_batches_done,
    extract_all_events,
    prepare_next_batch,
    run_batch_analysis,
    run_global_synthesis,
    segment_all_chapters,
    discover_tracking_dimensions,
)
from .output_writer import write_outputs

logger = logging.getLogger(__name__)


def run(
    *,
    project_id: str,
    data_manager: DataManager,
    tier: ModelTier = ModelTier.BALANCED,
    max_iterations: int = 30,
    max_chapters: int | None = None,
) -> str:
    """Execute story-deconstruction pipeline.

    Reads chapters from material-prep, runs the three-stage orchestrator
    (text-segmentation → event-extraction → batch-analysis), and writes
    standardized output files.

    Raises:
        FileNotFoundError: chapters.json not found in material-prep output.
        ValueError: chapters.json has invalid format.
    """
    start_time = time.monotonic()

    material_dir = data_manager.node_dir("material-prep")

    # ── Load upstream data ──
    chapters_path = material_dir / "chapters.json"
    novel_path = material_dir / "novel_standardized.md"

    if not chapters_path.exists():
        raise FileNotFoundError(
            f"chapters.json not found in material-prep output: {chapters_path}"
        )

    chapters_raw = json.loads(chapters_path.read_text(encoding="utf-8"))
    if not isinstance(chapters_raw, list):
        raise ValueError(f"chapters.json must be a JSON array, got {type(chapters_raw).__name__}")

    novel_text = ""
    if novel_path.exists():
        novel_text = novel_path.read_text(encoding="utf-8")
    else:
        logger.warning("novel_standardized.md not found at %s", novel_path)

    # ── Build chapter content from offsets ──
    chapters = []
    for ch in chapters_raw:
        ch_num = ch.get("index", ch.get("chapter_number", 0))
        start = ch.get("start", 0)
        end = ch.get("end", 0)
        content = novel_text[start:end] if novel_text and end > start else ""
        chapters.append({
            "chapter_number": ch_num,
            "title": ch.get("title", ""),
            "content": content,
        })

    if max_chapters is not None:
        chapters = chapters[:max_chapters]
        logger.info("max_chapters=%d applied, processing %d chapters", max_chapters, len(chapters))

    logger.info(
        "story-deconstruction starting: project=%s chapters=%d novel=%d chars",
        project_id,
        len(chapters),
        len(novel_text),
    )

    # ── Build orchestrator context ──
    context: dict = {
        "chapters": chapters,
        "project_id": project_id,
    }

    # ── Phase 1: Text segmentation ──
    logger.info("Phase 1: Text segmentation")
    segment_result = segment_all_chapters(context)
    logger.info("Segmentation: %s", segment_result)

    # ── Phase 2: Event extraction ──
    logger.info("Phase 2: Event extraction")
    extract_result = extract_all_events(context)
    logger.info("Extraction: %s", extract_result)

    # ── Phase 3: Discover tracking dimensions ──
    logger.info("Phase 3: Discover tracking dimensions")
    dim_result = discover_tracking_dimensions(context)
    logger.info("Dimensions: %s", dim_result)

    # ── Phase 4: Batch analysis loop ──
    logger.info("Phase 4: Batch analysis")
    batch_count = 0
    for _ in range(max_iterations):
        prepare_next_batch(context)
        status = check_all_batches_done(context)
        if status == "ALL_BATCHES_COMPLETE":
            break
        run_batch_analysis(context)
        batch_count += 1

    logger.info("Batch analysis completed: %d batches", batch_count)

    # ── Phase 5: Global synthesis ──
    logger.info("Phase 5: Global synthesis")
    synthesis_result = run_global_synthesis(context)
    logger.info("Synthesis: %s", synthesis_result)

    # ── Write standardized outputs ──
    logger.info("Writing standardized outputs")
    write_outputs(context, data_manager)

    elapsed = time.monotonic() - start_time
    total_events = context.get("total_events", 0)
    total_chapters = context.get("total_chapters", 0)

    summary = (
        f"story-deconstruction completed in {elapsed:.1f}s. "
        f"{total_chapters} chapters, {total_events} events, {batch_count} batches."
    )
    logger.info(summary)
    return summary
