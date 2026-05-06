"""Pure parsing utilities for schema-2.0 SKILL.md files.

Two functions matter to callers:

- ``parse_skill_file(path)`` — read+decode entry. Returns
  ``{"frontmatter": dict, "human_body": str}``. Pairs with
  ``serialize_skill`` (``core/serialize.py``) for byte-stable round-trip,
  which is what Studio UI ↔ Git synchronisation relies on.
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
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .exceptions import SkillLoadError

# 方针 3.2: lines reported by ruamel are 0-indexed *within* the
# YAML stream we hand it. ``parse_skill_file`` strips the opening
# ``---`` fence (line 1 of the SKILL.md) before parsing, so the YAML
# stream's line 0 corresponds to SKILL.md line 2.
_FRONTMATTER_LINE_OFFSET = 2


def _make_yaml() -> YAML:
    """Build a configured ruamel YAML loader.

    Round-trip mode (``typ='rt'``) preserves per-key line/column
    metadata on the returned ``CommentedMap`` / ``CommentedSeq`` —
    that is what ``locate_line_for_pydantic_loc`` walks.
    """
    yaml = YAML(typ="rt")
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
    yaml = _make_yaml()
    try:
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
        return content[match.end():].lstrip("\r\n")
    return content


def locate_line_for_pydantic_loc(
    root: Any, loc: Sequence[Any]
) -> int | None:
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


def parse_skill_file(path: Path | str) -> dict[str, Any]:
    """Read and decode a schema-2.0 SKILL.md file into its raw parts.

    Does *only* file I/O + YAML decoding. No semantic validation, no
    XML extraction, no ``<ref>`` resolution. Those concerns belong to
    ``SkillManifest.model_validate()`` and the compiler's rule pass.

    Args:
        path: Absolute or project-relative path to a ``SKILL.md``.

    Returns:
        ``{"frontmatter": CommentedMap, "human_body": str}``. The
        ``frontmatter`` value is a ruamel ``CommentedMap`` (dict
        subclass) carrying per-key ``.lc`` line metadata, ready to feed
        to ``SkillManifest.model_validate`` *and* to
        ``locate_line_for_pydantic_loc`` for line-resolved error
        reporting.

    Raises:
        SkillLoadError: Missing/malformed frontmatter or unreadable file.
    """
    p = Path(path)
    content = p.read_text(encoding="utf-8")

    frontmatter = _parse_frontmatter(content)
    # Cohesion plan 方针 3.3 (2026-04-26): YAML parses unquoted ``2.0``
    # as a Python float. Normalise to the canonical string so the
    # downstream Pydantic ``Literal["2.0"]`` discriminator sees the
    # right type and authors don't have to remember to quote the
    # version literal.
    if "schema_version" in frontmatter:
        frontmatter["schema_version"] = str(frontmatter["schema_version"]).strip()
    body = _strip_frontmatter(content)

    return {"frontmatter": frontmatter, "human_body": body}
