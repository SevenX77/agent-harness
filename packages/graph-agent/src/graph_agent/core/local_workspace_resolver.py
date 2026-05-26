"""Local filesystem implementation of the skill resolver protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from graph_agent.core.skill_resolver_protocol import (
    SkillResolutionError,
    SkillResolverProtocol,
    validate_skill_id,
)


class LocalWorkspaceResolver(SkillResolverProtocol):
    """Resolve skill ids from an ordered set of local workspace roots."""

    def __init__(self, search_paths: Iterable[str | Path] | None = None) -> None:
        paths = search_paths if search_paths is not None else (Path.cwd(), Path.cwd() / "skills")
        self.search_paths = tuple(Path(path) for path in paths)

    def resolve_skill(self, skill_id: str) -> Path:
        validate_skill_id(skill_id)
        relative_candidates = (Path(skill_id), Path(*skill_id.split(".")))
        matches: list[Path] = []
        for base in self.search_paths:
            for relative in relative_candidates:
                candidate = base / relative
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


__all__ = ["LocalWorkspaceResolver"]
