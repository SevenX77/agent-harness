"""Pure parsing utilities for V2.1 Markdown/YAML documents.

Parser helpers that matter to callers:

- ``parse_markdown_parts(path)`` — read+decode entry. Returns
  frontmatter, body, and line metadata for V2.1 markdown documents.
- ``_parse_frontmatter(content)`` / ``_strip_frontmatter(content)`` —
  internal helpers used by ``loader.py`` and ``compiler.py`` to peek
  ``schema_version`` before paying for full Pydantic validation.

Cohesion plan 方针 3.1 / 3.2 (2026-04-26): the frontmatter parser uses
``ruamel.yaml`` round-trip mode so the returned mapping carries
per-key line metadata (``CommentedMap.lc``). The compiler's
``ValidationError`` translation reads that metadata via
``locate_line_for_pydantic_loc`` to turn ``loc=('phases', 0, 'name')``
into a concrete ``SKILL.md:42`` location string.

Schema 1.x scaffolding (``<phase>``/``<node>`` regexes, ``<ref>``
resolution, legacy ``_validate_frontmatter``, XML tag extraction) was
removed in PR #6 — schema 2.0 has no XML body and Pydantic owns
structural validation.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

try:  # pragma: no cover - exercised indirectly depending on env deps
    from ruamel.yaml import YAML as _RuamelYAML
    from ruamel.yaml.error import YAMLError as _RuamelYAMLError

    RuamelYAML: Any = _RuamelYAML
    YAMLError: Any = _RuamelYAMLError
except ModuleNotFoundError:  # pragma: no cover
    import yaml

    RuamelYAML = None
    YAMLError = yaml.YAMLError

from graph_agent.core.exceptions import SkillLoadError, make_error_payload

# 方针 3.2: lines reported by ruamel are 0-indexed *within* the
# YAML stream we hand it. The opening ``---`` fence is stripped before
# parsing, so the YAML stream's line 0 corresponds to markdown line 2.
_FRONTMATTER_LINE_OFFSET = 2


def _make_yaml() -> Any:
    """Build a configured ruamel YAML loader.

    Round-trip mode (``typ='rt'``) preserves per-key line/column
    metadata on the returned ``CommentedMap`` / ``CommentedSeq`` —
    that is what ``locate_line_for_pydantic_loc`` walks.
    """
    if RuamelYAML is None:
        raise SkillLoadError("ruamel.yaml is not available")
    yaml = RuamelYAML(typ="rt")
    yaml.preserve_quotes = True
    return yaml


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content.

    Returns a ``CommentedMap`` (a dict subclass) so callers downstream
    can read line/column metadata via ``.lc.data[key]`` or via the
    helper :func:`locate_line_for_pydantic_loc`.
    """
    if not content.startswith("---"):
        raise SkillLoadError("No YAML frontmatter found (file must start with ---)")

    # Cohesion plan 方针 3.4 (2026-04-26): accept both ``\n`` and
    # ``\r\n``. ``read_text(...)`` normalises CRLF→LF, but Studio /
    # programmatic callers may hand us the raw bytes; the regex must
    # not depend on universal-newline normalisation.
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not match:
        raise SkillLoadError("Invalid frontmatter format")

    yaml_body = match.group(1)
    try:
        if RuamelYAML is None:
            import yaml as pyyaml

            data = pyyaml.safe_load(io.StringIO(yaml_body))
        else:
            yaml = _make_yaml()
            data = yaml.load(io.StringIO(yaml_body))
    except YAMLError as exc:
        raise SkillLoadError(f"Invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(data, dict):
        raise SkillLoadError("Frontmatter must be a YAML dictionary")

    return data


def _strip_frontmatter(content: str) -> str:
    """Return content after YAML frontmatter."""
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        return content[match.end() :].lstrip("\r\n")
    return content


def locate_line_for_pydantic_loc(root: Any, loc: Sequence[Any]) -> int | None:
    """Translate a Pydantic ``ValidationError.loc`` tuple into a
    1-indexed SKILL.md line number, or ``None`` if the path cannot be
    walked (e.g. mode-discriminator pseudo-segments like ``'graph'``
    that do not correspond to YAML keys).

    Pydantic 2 emits ``loc`` like ``('phases', 0, 'name')`` for a
    GraphSkillDef. For tagged unions it injects the tag as a pseudo
    path component (``('graph', 'phases', 0, ...)``) — those tag
    segments are skipped automatically when they don't resolve.

    ``root`` should be the ``CommentedMap`` returned by
    :func:`_parse_frontmatter`; passing a plain dict makes the helper
    return ``None`` (no line metadata available).
    """
    if root is None:
        return None

    node: Any = root
    last_line: int | None = None

    def _record(line0: int) -> None:
        nonlocal last_line
        last_line = line0 + _FRONTMATTER_LINE_OFFSET - 1  # convert to 1-indexed file line

    for segment in loc:
        if isinstance(node, dict):
            lc = getattr(node, "lc", None)
            data_map = getattr(lc, "data", None) if lc is not None else None
            if isinstance(segment, str) and segment in node:
                if data_map and segment in data_map:
                    _record(data_map[segment][0])
                node = node[segment]
                continue
            # Pydantic injects the discriminator tag (e.g. 'graph',
            # 'agent', 'persona', 'llm', 'logic', 'delegate') as a
            # virtual path component that does not exist in the YAML.
            # Skip these so the walk continues at the next real key.
            continue
        if isinstance(node, list):
            if isinstance(segment, int) and 0 <= segment < len(node):
                lc = getattr(node, "lc", None)
                if lc is not None and hasattr(lc, "item"):
                    try:
                        item_lc = lc.item(segment)
                    except (KeyError, IndexError):
                        item_lc = None
                    if item_lc:
                        _record(item_lc[0])
                node = node[segment]
                continue
            continue
        # Scalar reached but more loc segments remain — give up cleanly.
        break

    if last_line is None:
        return None
    return max(1, last_line + 1)  # 0-indexed → 1-indexed


def _fatal(path: Path, line: int, message: str) -> NoReturn:
    code = "[F-v3-graph-phase-id-invalid]"
    detail = f"{path}:{line} {message}"
    raise SkillLoadError(detail, payload=make_error_payload(code, detail, source_path=path))


def parse_markdown_parts(path: Path | str) -> tuple[dict[str, Any], str, dict[str, int]]:
    """Read a V2.1 markdown document into YAML frontmatter and raw body."""
    p = Path(path)
    content = p.read_text(encoding="utf-8")

    frontmatter = _parse_frontmatter(content)
    if "schema_version" in frontmatter:
        frontmatter["schema_version"] = str(frontmatter["schema_version"]).strip()
    body = _strip_frontmatter(content)
    frontmatter_end_line = 1
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        frontmatter_end_line = content[: match.end()].count("\n") + 1

    return frontmatter, body, {"body_start": frontmatter_end_line + 1}


def extract_raw_blocks(body: str, allowed_tags: list[str]) -> dict[str, str]:
    """Extract top-level ``<tag>...</tag>`` blocks as raw strings.

    The inside of each block is intentionally not parsed as XML.  Natural
    language angle brackets, HTML snippets, and malformed inner markup remain
    untouched.
    """
    blocks: dict[str, str] = {}
    for tag in allowed_tags:
        pattern = re.compile(
            rf"<{re.escape(tag)}(?:\s[^>]*)?>(.*?)</{re.escape(tag)}>",
            re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(body)
        if match:
            blocks[tag] = match.group(1).strip()
    return blocks


_FORBIDDEN_TOPOLOGY_TAG_RE = re.compile(
    r"</?\s*(phase|depends_on|edge)\b",
    re.IGNORECASE,
)


def scan_forbidden_topology_tags(path: Path, body: str) -> None:
    """Reject graph-topology tags inside phase XML bodies."""
    match = _FORBIDDEN_TOPOLOGY_TAG_RE.search(body)
    if match is None:
        return
    line = body[: match.start()].count("\n") + 1
    tag = match.group(0).replace(" ", "")
    if not tag.endswith(">"):
        tag += ">"
    _fatal(
        path,
        line,
        f"topology tag '{tag}' is forbidden in phase body (整图拓扑只能在 GRAPH.md)",
    )


__all__ = [
    "_parse_frontmatter",
    "_strip_frontmatter",
    "extract_raw_blocks",
    "locate_line_for_pydantic_loc",
    "parse_markdown_parts",
    "scan_forbidden_topology_tags",
]
