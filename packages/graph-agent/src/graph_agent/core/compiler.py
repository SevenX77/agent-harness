"""V2.1 public compile facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graph_agent.core.cache import compute_cache_key, load_from_cache, save_to_cache
from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.local_workspace_resolver import default_local_resolver_for_skill
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol


@dataclass
class CompileIssue:
    rule_id: str
    severity: str
    location: str
    message: str


@dataclass
class CompileResult:
    """Legacy diagnostic container retained for import compatibility."""

    issues: list[CompileIssue] = field(default_factory=list)

    @property
    def fatals(self) -> list[CompileIssue]:
        return [issue for issue in self.issues if issue.severity == "FATAL"]

    @property
    def warnings(self) -> list[CompileIssue]:
        return [issue for issue in self.issues if issue.severity == "WARNING"]

    @property
    def passed(self) -> bool:
        return not self.fatals


def compile_skill(
    root: str | Path,
    *,
    chat_model: Any = None,
    cache: bool = True,
    skill_resolver: SkillResolverProtocol | None = None,
) -> CompiledSkill:
    """Compile a V2.1 skill root into a CompiledSkill.

    ``chat_model`` is accepted for the stable T1.5 public signature; compilation itself
    is model-free. LangGraph assembly receives the model separately.
    """

    del chat_model
    skill_root = Path(root)
    resolver = skill_resolver or default_local_resolver_for_skill(skill_root)
    if cache:
        key = compute_cache_key(skill_root)
        cached = load_from_cache(key, skill_root)
        if cached is not None:
            return cached

    compiled = SkillLoader().compile_skill(skill_root, skill_resolver=resolver)
    if cache:
        save_to_cache(compute_cache_key(skill_root), compiled)
    return compiled


__all__ = ["CompileIssue", "CompileResult", "compile_skill"]
