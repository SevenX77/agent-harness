from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def prepare_chapter(inputs) -> dict:
    """Prepare chapter text with line numbers for LLM segmentation.

    Reads chapter_content and chapter_number from inputs and returns line-numbered
    preparation metadata.
    """
    chapter_content = inputs.get("chapter_content", "")
    chapter_number = inputs.get("chapter_number", 0)

    lines = chapter_content.split("\n")
    chapter_with_line_numbers = "\n".join([f"{i+1:4d}| {line}" for i, line in enumerate(lines)])

    logger.info("Prepared chapter %s with %d lines", chapter_number, len(lines))
    return {
        "chapter_with_line_numbers": chapter_with_line_numbers,
        "chapter_lines": lines,
        "chapter_number": chapter_number,
    }
