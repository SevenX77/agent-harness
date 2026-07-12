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
    """One compile diagnostic with explicit location axes.

    ``source_path`` is skill-relative (posix separators), ``line`` is the
    1-based line inside that file, ``field_path`` is the engine's nearest-field
    locator (e.g. ``"<phase>.depends_on"``) — consumers project these axes
    directly instead of parsing a location string.
    """

    rule_id: str
    severity: str
    source_path: str | None
    line: int | None
    field_path: str | None
    message: str


@dataclass
class CompileResult:
    """Aggregated compile diagnostics container (rides on the exception seam)."""

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
    runtime_input_fields: dict[str, set[str]] | None = None,
    allowed_roles: set[str] | None = None,
) -> CompiledSkill:
    """Compile a V2.1 skill root into a CompiledSkill.

    ``chat_model`` is accepted for the stable T1.5 public signature; compilation itself
    is model-free. LangGraph assembly receives the model separately.
    """

    del chat_model
    skill_root = Path(root)
    resolver = skill_resolver or default_local_resolver_for_skill(skill_root)
    if runtime_input_fields is not None:
        cache = False
    if cache:
        key = compute_cache_key(skill_root)
        cached = load_from_cache(key, skill_root)
        if cached is not None:
            return cached

    compiled = SkillLoader().compile_skill(
        skill_root,
        skill_resolver=resolver,
        runtime_input_fields=runtime_input_fields,
        allowed_roles=allowed_roles,
    )
    if cache:
        save_to_cache(compute_cache_key(skill_root), compiled)
    return compiled


__all__ = ["CompileIssue", "CompileResult", "compile_skill"]
