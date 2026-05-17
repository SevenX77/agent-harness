"""Token-level GRAPH.md serializer for Canvas round-trip editing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from graph_agent.core.loader import PhaseAttributeSpan, PhaseTokenInfo
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef

TokenKind = Literal["frontmatter", "comment", "io", "phase", "whitespace", "text"]

_PHASE_RE = re.compile(r"<phase\b([^>]*)/>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_IO_RE = re.compile(r"<(?:input|output)\b[^>]*/>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"([A-Za-z_][\w:-]*)\s*=\s*(['\"])(.*?)\2", re.DOTALL)


@dataclass(frozen=True)
class GraphToken:
    kind: TokenKind
    start: int
    end: int
    text: str
    phase_id: str | None = None
    phase_info: PhaseTokenInfo | None = None


def serialize_graph(manifest: GraphManifest, original_md: str | None = None) -> str:
    """Serialize a GraphManifest back to GRAPH.md Markdown.

    With ``original_md`` this performs token-level minimal rewrites of phase
    tags. Without it, a fresh canonical GRAPH.md is generated from the manifest.
    """

    if original_md is None:
        return _render_fresh_graph(manifest)
    return _serialize_with_original(manifest, original_md)


def _serialize_with_original(manifest: GraphManifest, original_md: str) -> str:
    tokens = _tokenize_graph(original_md)
    phase_by_id = {phase.id: phase for phase in manifest.phases}
    seen_phase_ids: set[str] = set()
    chunks: list[str] = []
    attachment_buffer: list[GraphToken] = []

    for token in tokens:
        if token.kind in {"frontmatter", "io"}:
            chunks.extend(buffered.text for buffered in attachment_buffer)
            attachment_buffer = []
            chunks.append(token.text)
            continue

        if token.kind != "phase" or token.phase_id is None or token.phase_info is None:
            attachment_buffer.append(token)
            continue

        phase = phase_by_id.get(token.phase_id)
        if phase is None:
            separator = _attachment_separator(attachment_buffer)
            if separator:
                chunks.append(separator)
            attachment_buffer = []
            continue

        chunks.extend(buffered.text for buffered in attachment_buffer)
        attachment_buffer = []
        seen_phase_ids.add(token.phase_id)
        chunks.append(_rewrite_phase_token(token, phase))

    additions = [phase for phase in manifest.phases if phase.id not in seen_phase_ids]
    if additions:
        chunks = _append_phase_lines(chunks, additions)
    if not additions or "".join(buffered.text for buffered in attachment_buffer).strip():
        chunks.extend(buffered.text for buffered in attachment_buffer)
    return "".join(chunks)


def _render_fresh_graph(manifest: GraphManifest) -> str:
    lines = [
        "---",
        'schema_version: "2.1"',
        f"name: {manifest.name}",
    ]
    if manifest.description:
        lines.append(f"description: {manifest.description}")
    lines.extend(
        [
            "---",
            f'<input src="{manifest.io_inputs_ref}" />',
            f'<output src="{manifest.io_outputs_ref}" />',
        ]
    )
    lines.extend(_phase_line(phase) for phase in manifest.phases)
    return "\n".join(lines) + "\n"


def _tokenize_graph(text: str) -> list[GraphToken]:
    matches: list[tuple[int, int, TokenKind, re.Match[str] | None]] = []
    frontmatter = re.match(r"^---\r?\n.*?\r?\n---", text, re.DOTALL)
    if frontmatter is not None:
        matches.append((frontmatter.start(), frontmatter.end(), "frontmatter", frontmatter))
    for match in _COMMENT_RE.finditer(text):
        matches.append((match.start(), match.end(), "comment", match))
    for match in _IO_RE.finditer(text):
        matches.append((match.start(), match.end(), "io", match))
    for match in _PHASE_RE.finditer(text):
        matches.append((match.start(), match.end(), "phase", match))
    matches.sort(key=lambda item: (item[0], item[1]))

    tokens: list[GraphToken] = []
    cursor = 0
    for start, end, kind, token_match in matches:
        if start < cursor:
            continue
        if cursor < start:
            tokens.extend(_text_or_whitespace_tokens(text, cursor, start))
        token_text = text[start:end]
        if kind == "phase" and token_match is not None:
            info = _phase_token_info(text, token_match)
            tokens.append(
                GraphToken(
                    kind="phase",
                    start=start,
                    end=end,
                    text=token_text,
                    phase_id=info.phase_id,
                    phase_info=info,
                )
            )
        else:
            tokens.append(GraphToken(kind=kind, start=start, end=end, text=token_text))
        cursor = end
    if cursor < len(text):
        tokens.extend(_text_or_whitespace_tokens(text, cursor, len(text)))
    return tokens


def _text_or_whitespace_tokens(text: str, start: int, end: int) -> list[GraphToken]:
    token_text = text[start:end]
    kind: TokenKind = "whitespace" if token_text.strip() == "" else "text"
    return [GraphToken(kind=kind, start=start, end=end, text=token_text)]


def _attachment_separator(tokens: list[GraphToken]) -> str:
    if not tokens:
        return ""
    text = "".join(token.text for token in tokens)
    if text.strip() == "":
        return ""
    if text.startswith("\r\n"):
        return "\r\n"
    if text.startswith("\n"):
        return "\n"
    return ""


def _phase_token_info(text: str, match: re.Match[str]) -> PhaseTokenInfo:
    raw_text = match.group(0)
    attrs_raw = match.group(1)
    attrs = {attr.group(1): attr.group(3) for attr in _ATTR_RE.finditer(attrs_raw)}
    phase_id = attrs.get("id", "")
    attr_raw_start = match.start(1)
    return PhaseTokenInfo(
        phase_id=phase_id,
        raw_text=raw_text,
        start_offset=match.start(),
        end_offset=match.end(),
        line_start=text[: match.start()].count("\n") + 1,
        line_end=text[: match.end()].count("\n") + 1,
        attrs=attrs,
        attr_spans=_phase_attr_spans(attrs_raw, attr_raw_start, text),
    )


def _phase_attr_spans(
    attrs_raw: str,
    attr_raw_start: int,
    graph_text: str,
) -> dict[str, PhaseAttributeSpan]:
    spans: dict[str, PhaseAttributeSpan] = {}
    for match in _ATTR_RE.finditer(attrs_raw):
        attr_start = attr_raw_start + match.start()
        attr_end = attr_raw_start + match.end()
        value_start = attr_raw_start + match.start(3)
        value_end = attr_raw_start + match.end(3)
        spans[match.group(1)] = PhaseAttributeSpan(
            name=match.group(1),
            value=match.group(3),
            quote=match.group(2),
            attr_start=attr_start,
            attr_end=attr_end,
            value_start=value_start,
            value_end=value_end,
            line_start=graph_text[:attr_start].count("\n") + 1,
            line_end=graph_text[:attr_end].count("\n") + 1,
        )
    return spans


def _rewrite_phase_token(token: GraphToken, phase: GraphPhaseRef) -> str:
    assert token.phase_info is not None
    original_depends_on = token.phase_info.attrs.get("depends_on", "")
    if phase.depends_on == _split_depends_on(original_depends_on):
        return token.text
    depends_on = _depends_on_text(phase)
    span = token.phase_info.attr_spans.get("depends_on")
    if span is None:
        return _insert_depends_on_attr(token.text, depends_on)
    relative_start = span.value_start - token.start
    relative_end = span.value_end - token.start
    return token.text[:relative_start] + depends_on + token.text[relative_end:]


def _insert_depends_on_attr(raw_text: str, depends_on: str) -> str:
    insert = f' depends_on="{depends_on}"'
    close_index = raw_text.rfind("/>")
    if close_index < 0:
        return raw_text
    return raw_text[:close_index].rstrip() + insert + " " + raw_text[close_index:]


def _append_phase_lines(chunks: list[str], phases: list[GraphPhaseRef]) -> list[str]:
    output = list(chunks)
    if output and not output[-1].endswith("\n"):
        output[-1] += "\n"
    for phase in phases:
        output.append(_phase_line(phase) + "\n")
    return output


def _phase_line(phase: GraphPhaseRef) -> str:
    return f'<phase id="{phase.id}" src="{phase.src}" depends_on="{_depends_on_text(phase)}" />'


def _depends_on_text(phase: GraphPhaseRef) -> str:
    return ",".join(phase.depends_on)


def _split_depends_on(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part for part in re.split(r"[\s,]+", raw.strip()) if part]


__all__ = ["GraphToken", "serialize_graph"]
