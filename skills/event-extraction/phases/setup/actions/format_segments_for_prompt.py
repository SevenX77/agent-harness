from graph_agent.cognitive.context_facade import Context


def format_segments_for_prompt(context: Context) -> None:
    """Format segmented paragraphs for event extraction prompts."""

    segmentation = dict(context.get("segmentation_result", {}) or {})
    paragraphs = list(segmentation.get("paragraphs", []))
    lines = []
    for para in paragraphs:
        index = para.get("index", "?") if isinstance(para, dict) else "?"
        para_type = para.get("type", "?") if isinstance(para, dict) else "?"
        start = para.get("start_line", "?") if isinstance(para, dict) else "?"
        end = para.get("end_line", "?") if isinstance(para, dict) else "?"
        content = para.get("content", para) if isinstance(para, dict) else para
        lines.append(f"段落{index}（{para_type}类，行{start}-{end}）：{content}")
    context.update(
        formatted_paragraphs="\n".join(lines),
        event_timeline={},
        events_raw="",
        parsed_events=[],
    )
