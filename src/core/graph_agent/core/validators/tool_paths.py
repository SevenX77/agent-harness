"""Static semantic validator: tool-path dot-reference resolvability.

See docs/superpowers/plans/2026-04-25-pr7-tool-paths-validator.md.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import AgentSkillDef, GraphSkillDef


def check_tool_paths(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Verify every tool-reference dot-path locates a real Python module."""
    raise NotImplementedError("filled in by Task 2 onward")
