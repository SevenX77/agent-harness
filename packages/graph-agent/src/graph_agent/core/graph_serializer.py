"""GRAPH.md serializer for V0.3.0 YAML frontmatter."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from graph_agent.core.loader import PhaseTokenInfo
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef, PhaseIOSchema

TokenKind = Literal["frontmatter", "comment", "phase", "whitespace", "text"]


@dataclass(frozen=True)
class GraphToken:
    kind: TokenKind
    start: int
    end: int
    text: str
    phase_id: str | None = None
    phase_info: PhaseTokenInfo | None = None


def serialize_graph(manifest: GraphManifest, original_md: str | None = None) -> str:
    """Serialize a GraphManifest back to canonical GRAPH.md Markdown."""

    rendered = _render_fresh_graph(manifest)
    if original_md is None:
        return rendered
    return _preserve_graph_markdown_topology(original_md, rendered)


def serialize_graph_topology(
    *,
    name: str,
    description: str | None,
    io: PhaseIOSchema,
    phases: Sequence[GraphPhaseRef],
    original_md: str | None = None,
) -> str:
    """Serialize a canvas topology snapshot to canonical GRAPH.md Markdown.

    Unlike :func:`serialize_graph` (which only sees ``manifest.phases`` as a
    ``list[str]`` and therefore cannot carry edges), this takes the full phase
    refs so the body ``<phase depends_on=...>`` elements reflect the REAL graph.

    - ``depends_on``: comma-joined; a phase with no deps renders ``depends_on="input"``
      (the reserved entry sentinel — the loader requires a non-empty ``depends_on``).
    - ``output``: derived as the leaf phases (ids that appear in no other phase's
      ``depends_on``), satisfying the FROZEN rules "at least one output" and
      "an output phase has no downstream edges".
    """
    downstream = {dep for phase in phases for dep in phase.depends_on}
    lines = [
        "---",
        'schema_version: "v0.3.0"',
        f"name: {name}",
    ]
    if description:
        lines.append(f"description: {description}")
    lines.append("io:")
    lines.extend(_render_mapping(io.model_dump(mode="json"), indent=2))
    lines.append("phases:")
    for phase in phases:
        lines.append(f"  - {phase.id}")
    lines.append("---")
    for phase in phases:
        depends_on = ", ".join(phase.depends_on) if phase.depends_on else "input"
        output = " output" if phase.id not in downstream else ""
        lines.append(f'<phase depends_on="{depends_on}"{output}>{phase.id}</phase>')
    rendered = "\n".join(lines) + "\n"
    if original_md is None:
        return rendered
    return _preserve_graph_markdown_topology(original_md, rendered)


def _render_fresh_graph(manifest: GraphManifest) -> str:
    lines = [
        "---",
        'schema_version: "v0.3.0"',
        f"name: {manifest.name}",
    ]
    if manifest.description:
        lines.append(f"description: {manifest.description}")
    lines.append("io:")
    lines.extend(_render_mapping(manifest.io.model_dump(mode="json"), indent=2))
    lines.append("phases:")
    for phase in manifest.phases:
        lines.append(f"  - {phase}")
    lines.append("---")
    for index, phase in enumerate(manifest.phases):
        depends_on = "input" if index == 0 else manifest.phases[index - 1]
        output = " output" if index == len(manifest.phases) - 1 else ""
        lines.append(f'<phase depends_on="{depends_on}"{output}>{phase}</phase>')
    return "\n".join(lines) + "\n"


_BODY_PHASE_RE = re.compile(r"<phase\b[^>]*>.*?</phase>", re.IGNORECASE | re.DOTALL)
_TOP_LEVEL_YAML_KEY_RE = re.compile(r"^[^\s#][^:]*:\s*.*$")


def _preserve_graph_markdown_topology(original_md: str, rendered_md: str) -> str:
    original_parts = _split_markdown_frontmatter(original_md)
    rendered_parts = _split_markdown_frontmatter(rendered_md)
    if original_parts is None or rendered_parts is None:
        return rendered_md

    original_frontmatter, original_body = original_parts
    rendered_frontmatter, rendered_body = rendered_parts
    rendered_phases_block = _extract_frontmatter_phases_block(rendered_frontmatter)
    if rendered_phases_block is None:
        return rendered_md

    merged_frontmatter = _replace_or_append_frontmatter_phases(
        original_frontmatter,
        rendered_phases_block.rstrip() + "\n",
    )
    merged_body = _replace_body_phase_tags(original_body, _rendered_phase_block(rendered_body))
    return f"---\n{merged_frontmatter.rstrip()}\n---\n{merged_body}"


def _split_markdown_frontmatter(markdown: str) -> tuple[str, str] | None:
    match = re.match(r"^---[ \t]*(?:\r?\n)", markdown)
    if match is None:
        return None
    frontmatter_start = match.end()
    closing = re.search(r"(?m)^---[ \t]*(?:\r?\n|$)", markdown[frontmatter_start:])
    if closing is None:
        return None
    frontmatter_end = frontmatter_start + closing.start()
    body_start = frontmatter_start + closing.end()
    return markdown[frontmatter_start:frontmatter_end], markdown[body_start:]


def _extract_frontmatter_phases_block(frontmatter: str) -> str | None:
    key_range = _frontmatter_top_level_key_range(frontmatter, "phases")
    if key_range is None:
        return None
    start, end = key_range
    return frontmatter[start:end]


def _replace_or_append_frontmatter_phases(frontmatter: str, phases_block: str) -> str:
    key_range = _frontmatter_top_level_key_range(frontmatter, "phases")
    if key_range is not None:
        start, end = key_range
        return f"{frontmatter[:start]}{phases_block}{frontmatter[end:]}"
    separator = "" if frontmatter.endswith("\n") else "\n"
    return f"{frontmatter}{separator}{phases_block}"


def _frontmatter_top_level_key_range(frontmatter: str, key: str) -> tuple[int, int] | None:
    lines = frontmatter.splitlines(keepends=True)
    offset = 0
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        key_match = re.match(rf"^{re.escape(key)}\s*:(.*)$", content)
        if key_match is None:
            offset += len(line)
            continue

        start = offset
        end = offset + len(line)
        trailing_value = key_match.group(1).strip()
        if trailing_value and not trailing_value.startswith("#"):
            return start, end

        for following in lines[index + 1 :]:
            if _is_top_level_yaml_key(following):
                break
            end += len(following)
        return start, end
    return None


def _is_top_level_yaml_key(line: str) -> bool:
    content = line.rstrip("\r\n")
    if not content or content.startswith((" ", "\t", "#")):
        return False
    return _TOP_LEVEL_YAML_KEY_RE.match(content) is not None


def _rendered_phase_block(rendered_body: str) -> str:
    phase_lines = [match.group(0).rstrip() for match in _BODY_PHASE_RE.finditer(rendered_body)]
    if not phase_lines:
        return rendered_body if rendered_body.endswith("\n") else f"{rendered_body}\n"
    return "\n".join(phase_lines) + "\n"


def _replace_body_phase_tags(body: str, phase_block: str) -> str:
    matches = list(_BODY_PHASE_RE.finditer(body))
    if not matches:
        prefix = "" if body.endswith("\n") or not body else "\n"
        return f"{body}{prefix}{phase_block}"

    phase_block = _with_newline_style(phase_block, _dominant_newline(body))
    chunks: list[str] = []
    last = 0
    inserted = False
    for match in matches:
        chunks.append(body[last : match.start()])
        if not inserted:
            if chunks[-1] and not chunks[-1].endswith("\n"):
                chunks.append("\n")
            chunks.append(phase_block)
            inserted = True
        last = match.end()
    chunks.append(body[last:])
    return "".join(chunks)


def _dominant_newline(text: str) -> str:
    crlf_count = text.count("\r\n")
    lf_count = text.count("\n") - crlf_count
    return "\r\n" if crlf_count > lf_count else "\n"


def _with_newline_style(text: str, newline: str) -> str:
    if newline == "\n":
        return text
    return text.replace("\n", newline)


def _render_mapping(value: object, *, indent: int) -> list[str]:
    prefix = " " * indent
    if not isinstance(value, dict):
        return [prefix + _scalar(value)]
    lines: list[str] = []
    for key, item in value.items():
        if isinstance(item, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_render_mapping(item, indent=indent + 2))
        elif isinstance(item, list):
            lines.append(f"{prefix}{key}:")
            for entry in item:
                lines.append(f"{prefix}  - {_scalar(entry)}")
        else:
            lines.append(f"{prefix}{key}: {_scalar(item)}")
    return lines


def _scalar(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        if value == "" or any(ch in value for ch in ":#[]{}"):
            return repr(value)
        return value
    return str(value)


__all__ = ["GraphToken", "serialize_graph", "serialize_graph_topology"]
