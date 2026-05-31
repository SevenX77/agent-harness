from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def prepare_chapter(context) -> dict:
    """Prepare chapter text with line numbers for LLM segmentation.

    Reads chapter_content and chapter_number from context, adds line numbers,
    and stores preparation metadata back in context.
    """
    chapter_content = context.get("chapter_content", "")
    chapter_number = context.get("chapter_number", 0)

    lines = chapter_content.split("\n")
    chapter_with_line_numbers = "\n".join([f"{i+1:4d}| {line}" for i, line in enumerate(lines)])

    context["chapter_with_line_numbers"] = chapter_with_line_numbers
    context["chapter_lines"] = lines
    context["chapter_number"] = chapter_number

    logger.info("Prepared chapter %s with %d lines", chapter_number, len(lines))
    return {}
