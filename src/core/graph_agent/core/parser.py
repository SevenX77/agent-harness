"""Pure parsing utilities for SKILL.md files.

Extracted from loader.py to allow shared use by both loader.py and compiler.py
without circular imports. All functions here are side-effect-free (except file reads
for ``<ref>`` resolution) and perform no dynamic module imports.

Schema 2.0 entry: ``parse_skill_file``
======================================

``parse_skill_file(path)`` returns the manifest as ``{"frontmatter": dict,
"human_body": str}`` and performs *only* file I/O + YAML decoding — no
schema validation, no XML extraction. Callers pass ``frontmatter`` to
``SkillManifest.model_validate()`` for semantic checking. ``human_body``
is the raw markdown after the closing ``---`` fence; downstream tools
may preserve it verbatim on re-serialisation (see ``core/serialize.py``).

Pairs with ``serialize_skill`` for byte-stable round-trip; the pair is
what Studio UI ↔ Git synchronisation relies on.

The rest of this module (XML tag extraction, ``<phase>/<node>``
normalisation, ``<ref>`` resolution, legacy ``_validate_frontmatter``)
is **schema 1.0 scaffolding** still required by the current
``loader.py`` / ``compiler.py`` pipeline. Task 0.3 Steps 2–4 will
migrate those call sites to the Manifest-driven flow and then this
scaffolding can be deleted.
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
# Graph mode: <phase> / <node> + <ref> patterns
# ---------------------------------------------------------------------------
# Task 5.3: SKILL.md now accepts <phase id="..."> as the canonical spelling;
# <node id="..."> stays supported so older skills keep loading during the
# terminology migration (see COGNITIVE_LOOP_GUIDE.md and Task 5.5). The
# compiler emits W-node-to-phase-migration to nudge authors toward the
# phase form.

_REF_PATTERN = re.compile(r'<ref\s+path="([^"]+)"\s*/>')

_NODE_PATTERN = re.compile(
    r'<node\s+id="([^"]+)"(?:\s+depends_on="([^"]+)")?\s*>(.*?)</node>',
    re.DOTALL,
)

# Task 5.3: SKILL.md now accepts <phase id="..."> as the canonical spelling;
# <node id="..."> stays supported for backwards compatibility during the
# terminology migration (see Task 5.5). Rather than branch the _NODE_PATTERN
# regex — which would shift its positional capture groups and break the two
# call sites in compiler.py / loader.py — we preprocess <phase> into <node>
# once at load time. Callers never see the original tag name.
_PHASE_OPEN_RE = re.compile(r'<phase(\s[^>]*)>')
_PHASE_CLOSE_RE = re.compile(r'</phase>')


def _normalise_phase_tags(content: str) -> str:
    """Rewrite ``<phase ...>...</phase>`` to ``<node ...>...</node>``.

    Keeps the two spellings semantically identical and lets the rest of
    the parser stay unchanged. Attributes (``id``, ``depends_on``) and
    whitespace are preserved verbatim.
    """
    content = _PHASE_OPEN_RE.sub(r'<node\1>', content)
    content = _PHASE_CLOSE_RE.sub(r'</node>', content)
    return content


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


# ---------------------------------------------------------------------------
# Schema 2.0 entry — pairs with core/serialize.py's ``serialize_skill``
# ---------------------------------------------------------------------------


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

