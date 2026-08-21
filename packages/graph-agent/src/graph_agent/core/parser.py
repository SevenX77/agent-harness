"""Pure parsing utilities for V2.1 Markdown/YAML documents.

Parser helpers that matter to callers:

- ``parse_markdown_parts(path)`` — read+decode entry. Returns
  frontmatter, body, and line metadata for V2.1 markdown documents.
- ``parse_markdown_parts_best_effort(path)`` — tolerant sibling for
  repair-view consumers (topology_projection) that must survive an
  unrelated duplicate-key defect elsewhere in the frontmatter; never use
  it on the compile/lint path, which must stay strict.
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

from graph_agent.core.authored_text import read_authored_text
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


def _parse_frontmatter(content: str, path: Path | None = None) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content.

    Returns a ``CommentedMap`` (a dict subclass) so callers downstream
    can read line/column metadata via ``.lc.data[key]`` or via the
    helper :func:`locate_line_for_pydantic_loc`.

    ``path`` is optional (call sites without a concrete file, e.g. the
    skill analyzer scanning raw text, pass ``None``) and is used only to
    prefix a raised :class:`SkillLoadError`'s message with ``path:line``
    when the underlying YAML error carries a location (see
    :func:`_format_frontmatter_yaml_error`).
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
        raise SkillLoadError(_format_frontmatter_yaml_error(exc, path)) from exc

    if not isinstance(data, dict):
        raise SkillLoadError("Frontmatter must be a YAML dictionary")

    return data


def _format_frontmatter_yaml_error(exc: YAMLError, path: Path | None) -> str:
    """Reformat a raw ruamel/pyyaml ``YAMLError`` into the repo's ``path:line`` convention.

    ``str(exc)`` embeds ruamel's own location dialect (`` in "<file>", line N,
    column M``), which none of the engine/Studio location regexes understand —
    they all expect a leading ``<path>:<line>`` (the same convention
    :func:`_fatal` below produces, and that
    ``apps/studio/backend/app/services/skills.py:_LOCATION_RE``/
    ``_location_file_from_error_message`` parse). Reformatting once here, where
    the raw exception is caught, fixes every downstream consumer instead of
    teaching each one ruamel's dialect.
    """
    line = _yaml_error_line(exc)
    if path is not None and line is not None:
        return f"{path}:{line} Invalid YAML in frontmatter: {exc}"
    return f"Invalid YAML in frontmatter: {exc}"


def _yaml_error_line(exc: YAMLError) -> int | None:
    """Convert a ruamel/pyyaml error mark's 0-indexed line to a 1-indexed file line.

    Prefers ``problem_mark`` (where the parser actually rejected the document,
    e.g. the *second* occurrence of a duplicate key) over ``context_mark``
    (where the surrounding construct started). Same offset as
    :data:`_FRONTMATTER_LINE_OFFSET` / :func:`locate_line_for_pydantic_loc`:
    the opening ``---`` fence is stripped before parsing, so YAML-stream line 0
    is markdown file line 2.
    """
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    line0 = getattr(mark, "line", None) if mark is not None else None
    if not isinstance(line0, int):
        return None
    return line0 + _FRONTMATTER_LINE_OFFSET


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
            next_node = _locate_dict_segment(node, segment, _record)
            if next_node is not _LOC_NOT_FOUND:
                node = next_node
                continue
            # Pydantic injects the discriminator tag (e.g. 'graph',
            # 'agent', 'persona', 'llm', 'logic', 'delegate') as a
            # virtual path component that does not exist in the YAML.
            # Skip these so the walk continues at the next real key.
            continue
        if isinstance(node, list):
            next_node = _locate_list_segment(node, segment, _record)
            if next_node is not _LOC_NOT_FOUND:
                node = next_node
                continue
            continue
        # Scalar reached but more loc segments remain — give up cleanly.
        break

    if last_line is None:
        return None
    return max(1, last_line + 1)  # 0-indexed → 1-indexed


_LOC_NOT_FOUND = object()


def _locate_dict_segment(
    node: dict[Any, Any],
    segment: Any,
    record: Any,
) -> Any:
    lc = getattr(node, "lc", None)
    data_map = getattr(lc, "data", None) if lc is not None else None
    if not isinstance(segment, str) or segment not in node:
        return _LOC_NOT_FOUND
    if data_map and segment in data_map:
        record(data_map[segment][0])
    return node[segment]


def _locate_list_segment(
    node: list[Any],
    segment: Any,
    record: Any,
) -> Any:
    if not isinstance(segment, int) or not 0 <= segment < len(node):
        return _LOC_NOT_FOUND
    lc = getattr(node, "lc", None)
    if lc is not None and hasattr(lc, "item"):
        try:
            item_lc = lc.item(segment)
        except (KeyError, IndexError):
            item_lc = None
        if item_lc:
            record(item_lc[0])
    return node[segment]


def _fatal(path: Path, line: int, message: str) -> NoReturn:
    code = "[F-v3-graph-phase-id-invalid]"
    detail = f"{path}:{line} {message}"
    raise SkillLoadError(
        detail,
        payload=make_error_payload(code, detail, source_path=_relative_source_path(path)),
    )


def _relative_source_path(path: Path) -> str:
    parts = path.parts
    if path.name == "GRAPH.md":
        return "GRAPH.md"
    for anchor in ("phases", "io"):
        if anchor in parts:
            index = len(parts) - 1 - parts[::-1].index(anchor)
            return Path(*parts[index:]).as_posix()
    return path.as_posix()


def _parse_error_code(path: Path) -> str:
    if path.name == "LOGIC.md":
        return "[F-v3-logic-schema-unknown-field]"
    if path.name == "SUBGRAPH.md":
        return "[F-v3-subgraph-schema-unknown-field]"
    if path.name == "SKILL.md":
        return "[F-v3-agent-schema-unknown-field]"
    return "[F-v3-graph-schema-unknown-field]"


def parse_markdown_parts(path: Path | str) -> tuple[dict[str, Any], str, dict[str, int]]:
    """Read a V2.1 markdown document into YAML frontmatter and raw body."""
    p = Path(path)
    content = read_authored_text(p)

    try:
        frontmatter = _parse_frontmatter(content, p)
    except SkillLoadError as exc:
        if exc.payload is not None:
            raise
        message = str(exc)
        raise SkillLoadError(
            message,
            payload=make_error_payload(
                _parse_error_code(p),
                message,
                source_path=_relative_source_path(p),
            ),
        ) from exc
    if "schema_version" in frontmatter:
        frontmatter["schema_version"] = str(frontmatter["schema_version"]).strip()
    body = _strip_frontmatter(content)
    frontmatter_end_line = 1
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        frontmatter_end_line = content[: match.end()].count("\n") + 1

    return frontmatter, body, {"body_start": frontmatter_end_line + 1}


def parse_markdown_parts_best_effort(path: Path | str) -> tuple[dict[str, Any], str, dict[str, int]]:
    """Best-effort sibling of :func:`parse_markdown_parts` for repair-view consumers.

    Compile/lint must stay strict — a duplicate mapping key (e.g. an
    accidental copy-paste under ``io.inputs.properties``) is a real defect the
    user needs to see and fix, so :func:`_parse_frontmatter` (the compile
    path) keeps rejecting it. But a *different* consumer —
    :func:`graph_agent.core.topology_projection.load_graph_topology_projection`,
    which exists solely to keep the phases/DAG visible in Studio's repair view
    while the user fixes a broken skill — has nothing to do with ``io`` at
    all. Under the strict parser, ruamel treats the whole frontmatter mapping
    as one atomic document: an unrelated duplicate key anywhere in ``io``
    blanks out the unrelated, syntactically-fine ``phases`` list too, which
    defeats the repair view's entire purpose (see
    ``docs/studio/mvp1/01_workflows/01_init.md`` D2: opening a non-standard
    skill must not block — "我们有 compile, 有 copilot" — the whole point is
    that the user can still see and repair it).

    This tolerates duplicate mapping keys (ruamel's ``allow_duplicate_keys``,
    last value wins) so callers that only need a subset of frontmatter
    fields can recover them; it still raises on YAML that is not just
    duplicate-keyed but genuinely malformed, so callers must not treat a
    successful parse here as validating the document.
    """
    p = Path(path)
    content = read_authored_text(p)

    if not content.startswith("---"):
        raise SkillLoadError("No YAML frontmatter found (file must start with ---)")
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
            yaml.allow_duplicate_keys = True
            data = yaml.load(io.StringIO(yaml_body))
    except YAMLError as exc:
        raise SkillLoadError(_format_frontmatter_yaml_error(exc, p)) from exc

    if not isinstance(data, dict):
        raise SkillLoadError("Frontmatter must be a YAML dictionary")

    body = _strip_frontmatter(content)
    frontmatter_end_line = 1
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        frontmatter_end_line = content[: match.end()].count("\n") + 1

    return data, body, {"body_start": frontmatter_end_line + 1}


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


def _body_offset_to_file_line(path: Path, body: str, offset: int) -> int:
    """File-absolute (frontmatter-inclusive) line for a 0-based offset into the
    frontmatter-stripped ``body``.

    Mirrors loader's ``_body_file_line`` so body diagnostics share the file axis
    frontmatter errors use (the editor marks the whole file). ``body`` is a suffix
    of the file content, so it anchors exactly; falls back to body-relative only
    when the file cannot be read.
    """
    try:
        content = read_authored_text(path)
    except OSError:
        return body[: max(0, offset)].count("\n") + 1
    if body:
        body_index = content.rfind(body)
        if body_index >= 0:
            return content[: body_index + max(0, offset)].count("\n") + 1
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        return content[: match.end()].count("\n") + 2
    return body[: max(0, offset)].count("\n") + 1


def scan_forbidden_topology_tags(path: Path, body: str) -> None:
    """Reject graph-topology tags inside phase XML bodies."""
    match = _FORBIDDEN_TOPOLOGY_TAG_RE.search(body)
    if match is None:
        return
    line = _body_offset_to_file_line(path, body, match.start())
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
