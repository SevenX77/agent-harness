"""Pure parsing utilities for schema-2.0 SKILL.md files.

Two functions matter to callers:

- ``parse_skill_file(path)`` — read+decode entry. Returns
  ``{"frontmatter": dict, "human_body": str}``. Pairs with
  ``serialize_skill`` (``core/serialize.py``) for byte-stable round-trip,
  which is what Studio UI ↔ Git synchronisation relies on.
- ``_parse_frontmatter(content)`` / ``_strip_frontmatter(content)`` —
  internal helpers used by ``loader.py`` and ``compiler.py`` to peek
  ``schema_version`` before paying for full Pydantic validation.

Schema 1.x scaffolding (``<phase>``/``<node>`` regexes, ``<ref>``
resolution, legacy ``_validate_frontmatter``, XML tag extraction) was
removed in PR #6 — schema 2.0 has no XML body and Pydantic owns
structural validation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .exceptions import SkillLoadError


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        raise SkillLoadError("No YAML frontmatter found (file must start with ---)")

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        raise SkillLoadError("Invalid frontmatter format")

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillLoadError(f"Invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(data, dict):
        raise SkillLoadError("Frontmatter must be a YAML dictionary")

    return data


def _strip_frontmatter(content: str) -> str:
    """Return content after YAML frontmatter."""
    match = re.match(r"^---\n.*?\n---", content, re.DOTALL)
    if match:
        return content[match.end():].lstrip("\n")
    return content


def parse_skill_file(path: Path | str) -> dict[str, Any]:
    """Read and decode a schema-2.0 SKILL.md file into its raw parts.

    Does *only* file I/O + YAML decoding. No semantic validation, no
    XML extraction, no ``<ref>`` resolution. Those concerns belong to
    ``SkillManifest.model_validate()`` and the compiler's rule pass.

    Args:
        path: Absolute or project-relative path to a ``SKILL.md``.

    Returns:
        ``{"frontmatter": dict, "human_body": str}`` where
        ``frontmatter`` is the YAML-decoded dict between the ``---``
        fences (ready to feed to ``SkillManifest.model_validate``) and
        ``human_body`` is the markdown text after the closing fence
        (may be empty).

    Raises:
        SkillLoadError: Missing/malformed frontmatter or unreadable file.
    """
    p = Path(path)
    content = p.read_text(encoding="utf-8")

    frontmatter = _parse_frontmatter(content)
    body = _strip_frontmatter(content)

    return {"frontmatter": frontmatter, "human_body": body}

