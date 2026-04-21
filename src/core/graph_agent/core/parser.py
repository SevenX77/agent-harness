"""Pure parsing utilities for SKILL.md files.

Extracted from loader.py to allow shared use by both loader.py and compiler.py
without circular imports. All functions here are side-effect-free (except file reads
for ``<ref>`` resolution) and perform no dynamic module imports.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .exceptions import SkillLoadError

# ---------------------------------------------------------------------------
# Frontmatter validation (adapted from DeerFlow skills/validation.py)
# ---------------------------------------------------------------------------
# NOTE: This allowed-key set is intentionally different from deerflow/skills/validation.py.
# DeerFlow's set covers discovery-layer metadata (allowed-tools, compatibility);
# this set covers orchestration-layer declarations (type, io, context_mapping).
# Both share the common base keys (name, description, license, version, author, metadata).

_ALLOWED_FRONTMATTER = {
    "name", "description", "license", "version", "author", "metadata",
    "type", "io", "context_mapping",
}


def _validate_frontmatter(frontmatter: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Validate SKILL.md frontmatter fields.

    Adapted from DeerFlow skills/validation.py L15-85.
    """
    unexpected = set(frontmatter.keys()) - _ALLOWED_FRONTMATTER
    if unexpected:
        return False, f"Unexpected frontmatter keys: {', '.join(sorted(unexpected))}", None

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter", None
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter", None

    name = frontmatter["name"]
    if not isinstance(name, str) or not name.strip():
        return False, "Name must be a non-empty string", None

    name = name.strip()
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, f"Name '{name}' should be hyphen-case (lowercase, digits, hyphens)", None
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"Name '{name}' has invalid hyphen placement", None
    if len(name) > 64:
        return False, f"Name too long ({len(name)} chars, max 64)", None

    description = frontmatter.get("description", "")
    if isinstance(description, str) and len(description) > 1024:
        return False, f"Description too long ({len(description)} chars, max 1024)", None

    return True, "Valid", name


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


# ---------------------------------------------------------------------------
# XML tag extraction
# ---------------------------------------------------------------------------

_ALLOWED_SECTION_TAGS = (
    "phase_config",
    "system_prompt",
    "user_prompt_builder",
    "user_prompt",
    "data_architecture",
)

_TAG_PATTERN = re.compile(
    r"(?ms)^[ \t]*<("
    + "|".join(_ALLOWED_SECTION_TAGS)
    + r")>\s*\n?(.*)\n?[ \t]*</\1>[ \t]*$"
)


def _extract_tags(content: str) -> dict[str, list[str]]:
    """Extract all custom XML tags from markdown content.

    Returns a dict mapping tag_name -> list of content strings.
    """
    body = _strip_frontmatter(content)
    if not body.strip():
        return {}

    tags: dict[str, list[str]] = {}
    for match in _TAG_PATTERN.finditer(body):
        tag_name = match.group(1)
        tag_content = match.group(2).strip()
        tags.setdefault(tag_name, []).append(tag_content)
    return tags


# ---------------------------------------------------------------------------
# Phase grouping by ## header
# ---------------------------------------------------------------------------

_PHASE_HEADER_PATTERN = re.compile(r"^##\s+Phase\s+\d+:\s*(.+)$", re.MULTILINE)


def _split_by_phase_headers(content: str) -> list[tuple[str, str]]:
    """Split content into (phase_title, section_text) pairs.

    Each section runs from its ## Phase header to the next ## header.
    """
    body = _strip_frontmatter(content)
    matches = list(_PHASE_HEADER_PATTERN.finditer(body))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append((title, body[start:end]))

    return sections


# ---------------------------------------------------------------------------
# Graph mode: <node> + <ref> patterns
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r'<ref\s+path="([^"]+)"\s*/>')

_NODE_PATTERN = re.compile(
    r'<node\s+id="([^"]+)"(?:\s+depends_on="([^"]+)")?\s*>(.*?)</node>',
    re.DOTALL,
)


def _resolve_refs(content: str, base_dir: Path, *, _depth: int = 0) -> str:
    """Recursively resolve ``<ref path="..." />`` tags to file contents."""
    if _depth > 10:
        raise SkillLoadError("Ref resolution exceeded maximum depth (10)")

    def replacer(match: re.Match[str]) -> str:
        ref_path = base_dir / match.group(1)
        resolved = ref_path.resolve()
        if not resolved.is_relative_to(base_dir.resolve()):
            raise SkillLoadError(
                f"Ref path escapes skill directory: {match.group(1)}"
            )
        if not ref_path.exists():
            raise SkillLoadError(f"Referenced file not found: {ref_path}")
        ref_content = ref_path.read_text(encoding="utf-8")
        return _resolve_refs(ref_content, ref_path.parent, _depth=_depth + 1)

    return _REF_PATTERN.sub(replacer, content)
