"""Static Skill Studio template library."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.models.templates import SkillTemplate

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def list_templates() -> list[SkillTemplate]:
    """Return built-in SKILL.md templates sorted by id."""
    templates: list[SkillTemplate] = []
    for path in sorted(TEMPLATE_DIR.glob("*.SKILL.md")):
        content = path.read_text(encoding="utf-8")
        frontmatter = _frontmatter(path)
        templates.append(
            SkillTemplate(
                id=path.name.removesuffix(".SKILL.md"),
                name=str(frontmatter.get("name") or path.stem),
                description=str(frontmatter.get("description") or ""),
                type=str(frontmatter.get("type") or "graph"),
                content=content,
            ),
        )
    return templates


def _frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    try:
        _, raw_frontmatter, _ = content.split("---", 2)
    except ValueError:
        return {}
    parsed = yaml.safe_load(raw_frontmatter) or {}
    return dict(parsed) if isinstance(parsed, dict) else {}
