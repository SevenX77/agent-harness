"""Local filesystem implementation of the skill resolver protocol."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from graph_agent.core.skill_resolver_protocol import (
    SkillResolutionError,
    SkillResolverProtocol,
    validate_skill_id,
)


class LocalWorkspaceResolver(SkillResolverProtocol):
    """Resolve skill ids from an ordered set of local workspace roots."""

    def __init__(self, search_paths: Iterable[str | Path] | None = None) -> None:
        paths = search_paths if search_paths is not None else (Path.cwd(), Path.cwd() / "skills")
        self.search_paths = _dedupe_paths(paths)

    def resolve_skill(self, skill_id: str) -> Path:
        validate_skill_id(skill_id)
        relative_candidates = (Path(skill_id), Path(*skill_id.split(".")))
        matches: list[Path] = []
        for base in self.search_paths:
            for relative in relative_candidates:
                candidate = _candidate_under_base(base, relative)
                if candidate is None:
                    continue
                if candidate.is_dir() and (candidate / "GRAPH.md").is_file():
                    matches.append(candidate)

        unique_matches = tuple(dict.fromkeys(path.resolve() for path in matches))
        if len(unique_matches) == 1:
            return unique_matches[0]
        if len(unique_matches) > 1:
            paths = ", ".join(str(path) for path in unique_matches)
            raise SkillResolutionError(
                skill_id,
                f"ambiguous skill id; matches: {paths}",
                code="[F-v3-skill-id-ambiguous]",
            )

        searched = ", ".join(str(path) for path in self.search_paths)
        raise SkillResolutionError(
            skill_id,
            f"not registered in search paths: {searched}",
            code="[F-v3-skill-not-registered]",
        )


def default_local_resolver_for_skill(skill_path: str | Path) -> LocalWorkspaceResolver:
    """Build a local resolver rooted around a skill under direct SDK execution."""

    root = _skill_root_from_entrypoint(skill_path)
    return LocalWorkspaceResolver(_default_search_paths(root))


def default_local_resolver_for_compiled(compiled: Any) -> LocalWorkspaceResolver:
    """Build a local resolver from a ``CompiledSkill`` when assembly is called directly."""

    roots: list[Path] = []
    nodes = getattr(compiled, "nodes", ())
    for node in nodes:
        path = getattr(node, "path", None)
        if path is None:
            continue
        phase_path = _normalize_path(path)
        try:
            roots.append(phase_path.parents[2])
        except IndexError:
            roots.append(phase_path.parent)
    roots.extend((Path.cwd(), Path.cwd() / "skills"))
    search_paths: list[Path] = []
    for root in roots:
        search_paths.extend(_default_search_paths(root))
    return LocalWorkspaceResolver(search_paths)


def _default_search_paths(root: Path) -> tuple[Path, ...]:
    return (
        root,
        root / "skills",
        root / "registry",
        root.parent,
        root.parent / "skills",
        root.parent / "registry",
        Path.cwd(),
        Path.cwd() / "skills",
        Path.cwd() / "registry",
    )


def _skill_root_from_entrypoint(skill_path: str | Path) -> Path:
    entrypoint = _normalize_path(skill_path)
    if entrypoint.name in {"GRAPH.md", "SKILL.md"}:
        return entrypoint.parent
    return entrypoint


def _candidate_under_base(base: Path, relative: Path) -> Path | None:
    try:
        # codeql[py/path-injection] relative is derived from validate_skill_id and bounded below.
        candidate = (base / relative).resolve()
        candidate.relative_to(base)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def _normalize_path(path: str | Path) -> Path:
    return Path(os.path.normpath(os.fspath(path)))


def _dedupe_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = _normalize_path(path)
        key = os.path.normcase(os.fspath(resolved))
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return tuple(unique)


__all__ = [
    "LocalWorkspaceResolver",
    "default_local_resolver_for_compiled",
    "default_local_resolver_for_skill",
]
