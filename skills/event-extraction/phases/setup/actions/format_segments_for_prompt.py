import logging

logger = logging.getLogger(__name__)


def format_segments_for_prompt(inputs) -> dict:
    """Format segmented paragraphs as markdown for LLM prompt."""
    segmentation = inputs.get("segmentation_result", {})
    paragraphs = segmentation.get("paragraphs", [])

    lines = []
    for para in paragraphs:
        para_type = para.get("type", "B")
        type_name = {"A": "A类-设定", "B": "B类-事件", "C": "C类-系统"}.get(
            para_type, para_type
        )
        lines.append(f"### 段落 {para.get('index', 0)} [{type_name}]")
        lines.append("")
        lines.append(para.get("content", ""))
        lines.append("")
        lines.append("---")
        lines.append("")

    formatted = "\n".join(lines)
    logger.info(f"Formatted {len(paragraphs)} paragraphs")
    return {"formatted_paragraphs": formatted}
