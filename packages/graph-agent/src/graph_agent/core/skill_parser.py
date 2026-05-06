"""Phase 1 SKILL.md text parsing for the loader pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.parser import _parse_frontmatter, _strip_frontmatter

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_OUTPUT_SCHEMA_TITLE_RE = re.compile(
    r"\boutput[\s_-]*schema(?:[\s_-]*md)?\b",
    re.IGNORECASE,
)
_OUTPUT_EXAMPLE_TITLE_RE = re.compile(
    r"\boutput[\s_-]*example(?:[\s_-]*md)?\b",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


@dataclass(frozen=True)
class _SchemaMarkdownBlock:
    """One body markdown block that declares a phase output schema/example."""

    phase_name: str
    field_name: str
    heading_line: int
    heading_level: int
    content_start: int


def parse_skill_md(text: str) -> dict[str, Any]:
    """Phase 1: SKILL.md text to a plain raw manifest dict.

    This function performs only textual/YAML splitting and field
    normalisation. It does not instantiate Pydantic models and does not
    call SchemaEngine.
    """
    if not text.strip():
        raise SkillLoadError("SKILL.md is empty")

    raw = _to_builtin_dict(_parse_frontmatter(text))
    if "schema_version" in raw:
        raw["schema_version"] = str(raw["schema_version"]).strip()
    _mirror_phase_schema_markdown(raw)
    _apply_markdown_schema_blocks(raw, _strip_frontmatter(text))
    return raw


def _to_builtin_dict(value: Any) -> dict[str, Any]:
    converted = _to_builtin(value)
    if not isinstance(converted, dict):
        raise SkillLoadError("Frontmatter must be a YAML dictionary")
    return converted


def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_builtin(v) for v in value]
    return value


def _mirror_phase_schema_markdown(raw: dict[str, Any]) -> None:
    phases = raw.get("phases")
    if not isinstance(phases, list):
        return
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        output_example = phase.get("output_example")
        if isinstance(output_example, str) and "output_example_md" not in phase:
            phase["output_example_md"] = output_example
        output_schema = phase.get("output_schema")
        if (
            isinstance(output_schema, str)
            and "output_schema_md" not in phase
            and _looks_like_schema_markdown(output_schema)
        ):
            phase["output_schema_md"] = output_schema
            phase.pop("output_schema", None)


def _apply_markdown_schema_blocks(raw: dict[str, Any], body: str) -> None:
    phases = raw.get("phases")
    if not isinstance(phases, list) or not body.strip():
        return

    phase_by_name = _phase_dicts_by_name(phases)
    blocks = _find_schema_markdown_blocks(body, list(phase_by_name))
    if not blocks:
        return

    lines = body.splitlines(keepends=True)
    for index, block in enumerate(blocks):
        next_block_start = blocks[index + 1].heading_line if index + 1 < len(blocks) else len(lines)
        raw_content = _extract_schema_block_content(
            lines[block.content_start : next_block_start],
            block.field_name,
            block.heading_level,
        )
        content = raw_content.strip("\r\n")
        if not content.strip():
            raise SkillLoadError(
                f"Markdown block for phase '{block.phase_name}' {block.field_name} is empty"
            )

        phase = phase_by_name[block.phase_name]
        _set_phase_schema_markdown(phase, block, content)


def _phase_dicts_by_name(phases: list[Any]) -> dict[str, dict[str, Any]]:
    phase_by_name: dict[str, dict[str, Any]] = {}
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = phase.get("name")
        if not isinstance(name, str) or not name:
            continue
        if name in phase_by_name:
            raise SkillLoadError(f"Duplicate phase name in raw manifest: {name!r}")
        phase_by_name[name] = phase
    return phase_by_name


def _find_schema_markdown_blocks(
    body: str,
    phase_names: list[str],
) -> list[_SchemaMarkdownBlock]:
    lines = body.splitlines(keepends=True)
    blocks: list[_SchemaMarkdownBlock] = []
    current_phase: str | None = None

    for line_index, raw_line in enumerate(lines):
        heading = _parse_markdown_heading(raw_line)
        if heading is None:
            continue
        level, title = heading
        schema_field = _schema_field_from_title(title)
        if schema_field is None:
            context_phase = _phase_context_from_heading(title, phase_names)
            if context_phase is not None:
                current_phase = context_phase
            continue

        phase_name = _phase_name_from_schema_heading(
            title,
            phase_names,
            current_phase,
        )
        blocks.append(
            _SchemaMarkdownBlock(
                phase_name=phase_name,
                field_name=schema_field,
                heading_line=line_index,
                heading_level=level,
                content_start=line_index + 1,
            )
        )
    return blocks


def _parse_markdown_heading(line: str) -> tuple[int, str] | None:
    match = _MARKDOWN_HEADING_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    return len(match.group(1)), match.group(2).strip()


def _schema_field_from_title(title: str) -> str | None:
    if _OUTPUT_SCHEMA_TITLE_RE.search(title):
        return "output_schema_md"
    if _OUTPUT_EXAMPLE_TITLE_RE.search(title):
        return "output_example_md"

    normalized = _normalize_heading_text(title)
    if normalized == "schema":
        return "output_schema_md"
    if normalized == "example":
        return "output_example_md"
    return None


def _phase_context_from_heading(title: str, phase_names: list[str]) -> str | None:
    cleaned = re.sub(r"^\s*phases?\s*[:#-]\s*", "", title, flags=re.IGNORECASE)
    return _match_phase_name(cleaned, phase_names)


def _phase_name_from_schema_heading(
    title: str,
    phase_names: list[str],
    current_phase: str | None,
) -> str:
    remainder = _OUTPUT_SCHEMA_TITLE_RE.sub(" ", title)
    remainder = _OUTPUT_EXAMPLE_TITLE_RE.sub(" ", remainder)
    remainder = re.sub(r"\b(phases?|for|of|md)\b", " ", remainder, flags=re.IGNORECASE)
    phase_name = _match_phase_name(remainder, phase_names)
    if phase_name is not None:
        return phase_name
    if _normalize_heading_text(remainder):
        raise SkillLoadError(f"Markdown schema heading names an unknown phase: {title!r}")
    if current_phase is not None:
        return current_phase
    if len(phase_names) == 1:
        return phase_names[0]

    field = _schema_field_from_title(title) or "schema block"
    raise SkillLoadError(
        f"Markdown {field} heading must name one phase when multiple phases exist: {title!r}"
    )


def _match_phase_name(candidate: str, phase_names: list[str]) -> str | None:
    cleaned = _clean_heading_remainder(candidate)
    normalized = _normalize_heading_text(cleaned)
    if not normalized:
        return None
    for phase_name in phase_names:
        if normalized == _normalize_heading_text(phase_name):
            return phase_name
    return None


def _clean_heading_remainder(value: str) -> str:
    cleaned = value.strip()
    cleaned = cleaned.strip("`'\"[](){}")
    cleaned = re.sub(r"^[\s:./\\|_-]+|[\s:./\\|_-]+$", "", cleaned)
    return cleaned


def _normalize_heading_text(value: str) -> str:
    cleaned = _clean_heading_remainder(value).lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", " ", cleaned)
    cleaned = re.sub(r"[\s_]+", "-", cleaned).strip("-")
    return cleaned


def _extract_schema_block_content(
    lines: list[str],
    field_name: str,
    heading_level: int,
) -> str:
    if field_name == "output_example_md":
        return _trim_after_output_example(lines)
    return _trim_output_schema_lines(lines, heading_level)


def _trim_after_output_example(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if "</output_example>" in line:
            return "".join(lines[: index + 1])
    return _trim_at_markdown_heading(lines, 2)


def _trim_output_schema_lines(lines: list[str], heading_level: int) -> str:
    first_content = _first_nonblank_line_index(lines)
    if first_content is not None:
        fence_match = _FENCE_RE.match(lines[first_content])
        if fence_match is not None:
            fence = fence_match.group(1)[0] * 3
            for index in range(first_content + 1, len(lines)):
                if lines[index].lstrip().startswith(fence):
                    return "".join(lines[: index + 1])
    return _trim_at_markdown_heading(lines, heading_level)


def _first_nonblank_line_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.strip():
            return index
    return None


def _trim_at_markdown_heading(lines: list[str], max_level: int) -> str:
    for index, line in enumerate(lines):
        heading = _parse_markdown_heading(line)
        if heading is not None and heading[0] <= max_level:
            return "".join(lines[:index])
    return "".join(lines)


def _set_phase_schema_markdown(
    phase: dict[str, Any],
    block: _SchemaMarkdownBlock,
    content: str,
) -> None:
    if block.field_name in phase:
        raise SkillLoadError(f"Duplicate {block.field_name} for phase '{block.phase_name}'")
    if block.field_name == "output_schema_md" and phase.get("output_schema"):
        raise SkillLoadError(f"Duplicate output_schema for phase '{block.phase_name}'")
    if block.field_name == "output_example_md":
        if phase.get("output_example"):
            raise SkillLoadError(f"Duplicate output_example for phase '{block.phase_name}'")
        phase["output_example"] = content
    phase[block.field_name] = content


def _looks_like_schema_markdown(value: str) -> bool:
    stripped = value.strip()
    return (
        "\n" in stripped
        or ":" in stripped
        or stripped.startswith("{")
        or "<output_example" in stripped
    )


__all__ = ["parse_skill_md"]
