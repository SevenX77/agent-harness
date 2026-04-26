"""Skill frontmatter validation utilities.

Pure-logic validation of SKILL.md frontmatter — no FastAPI or HTTP dependencies.

This module belongs to the **discovery layer** (deerflow registry / skill
upload) — its only job is to surface skills' identity (name, description) and
compatibility metadata. Orchestration-layer fields (``schema_version``,
``type``, ``io``, ``phases``, ``agent_profile``, ...) are validated by
``graph_agent.core.manifest.SkillManifest`` and are deliberately ignored
here. Adding them to ``ALLOWED_FRONTMATTER_PROPERTIES`` would couple the
discovery layer to every future orchestration-vocabulary change; instead
this module silently passes through unknown keys and only enforces the
discovery contract on its own keys.
"""

import re
from pathlib import Path

import yaml

# Discovery-layer keys this validator actively enforces (name, description,
# compatibility, etc.). Orchestration-layer keys are intentionally not in
# this set — the deerflow registry does not care about them, and the
# orchestration layer (graph_agent.core.manifest.SkillManifest) validates
# them in its own pipeline. Unknown keys are silently allowed.
ALLOWED_FRONTMATTER_PROPERTIES = {"name", "description", "license", "allowed-tools", "metadata", "compatibility", "version", "author"}


def _validate_skill_frontmatter(skill_dir: Path) -> tuple[bool, str, str | None]:
    """Validate a skill directory's SKILL.md frontmatter.

    Args:
        skill_dir: Path to the skill directory containing SKILL.md.

    Returns:
        Tuple of (is_valid, message, skill_name).
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found", None

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found", None

    # Extract frontmatter
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format", None

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary", None
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}", None

    # NOTE: Unknown keys are intentionally allowed (see module docstring) —
    # schema 2.0 orchestration keys (schema_version, type, io, phases, ...)
    # pass through this discovery-layer validator untouched. The orchestration
    # layer (graph_agent.core.manifest.SkillManifest) is the authoritative
    # validator for those keys.

    # Check required fields
    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter", None
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter", None

    # Validate name
    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}", None
    name = name.strip()
    if not name:
        return False, "Name cannot be empty", None

    # Check naming convention (hyphen-case: lowercase with hyphens)
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)", None
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens", None
    if len(name) > 64:
        return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters.", None

    # Validate description
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}", None
    description = description.strip()
    if description:
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)", None
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters.", None

    return True, "Skill is valid!", name
