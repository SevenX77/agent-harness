"""Static Skill Studio template library."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.core.parser import parse_skill_file

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
    return dict(parse_skill_file(path)["frontmatter"])

