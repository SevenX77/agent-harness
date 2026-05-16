"""V2.1 loader compatibility module.

The old schema-2.0 pipeline used ``skill_parser.py`` for single-file
``SKILL.md`` parsing.  V2.1 routes skill-root directories through
``loader.py``; this module gives future callers an explicit V2.1 import
surface without reviving the old parser API.
"""

from __future__ import annotations

from graph_agent.core.loader import CompiledSkill, PhaseDocument, SkillLoader

__all__ = ["CompiledSkill", "PhaseDocument", "SkillLoader"]
