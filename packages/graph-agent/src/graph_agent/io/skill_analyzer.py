"""Skill Analyzer utilities for SKILL.md frontmatter.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core.parser import _parse_frontmatter

logger = logging.getLogger(__name__)


# ── Frontmatter parsing ──────────────────────────────────────────────────────


def parse_frontmatter(skill_path: str | Path) -> dict[str, Any]:
    """Parse YAML frontmatter from a SKILL.md file.

    Args:
        skill_path: Path to SKILL.md file.

    Returns:
        Parsed frontmatter dict.

    Raises:
        FileNotFoundError: If skill_path doesn't exist.
        SkillLoadError: If frontmatter is malformed.
    """
    path = Path(skill_path)
    if not path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {path}")

    text = path.read_text(encoding="utf-8")
    return _parse_frontmatter(text)


def get_skill_type(skill_path: str | Path) -> str:
    """Get the execution type of a SKILL.md.

    Returns:
        "simple" or "graph"
    """
    fm = parse_frontmatter(skill_path)
    return str(fm.get("type", "simple"))
