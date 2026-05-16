from graph_agent.cognitive.context_facade import Context


def prepare_chapter(context: Context) -> None:
    """Prepare chapter text with stable line numbers for segmentation."""

    chapter_content = str(context.get("chapter_content", ""))
    chapter_number = context.get("chapter_number", 0)
    lines = chapter_content.splitlines() or [chapter_content]
    chapter_with_line_numbers = "\n".join(
        f"{index + 1:4d}| {line}" for index, line in enumerate(lines)
    )
    context.update(
        chapter_content=chapter_content,
        chapter_number=chapter_number,
        chapter_lines=lines,
        chapter_with_line_numbers=chapter_with_line_numbers,
    )
