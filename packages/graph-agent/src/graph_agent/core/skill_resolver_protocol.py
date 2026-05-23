"""Skill resolver protocol for V0.3.0 skill-id based composition."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from graph_agent.core.exceptions import SkillLoadError

SKILL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
SKILL_ID_RE = re.compile(SKILL_ID_PATTERN)


class SkillResolutionError(SkillLoadError):
    """Raised when a declared target_skill cannot be resolved to a skill root."""

    def __init__(
        self,
        skill_id: str,
        reason: str,
        *,
        code: str = "[F-v3-skill-not-registered]",
    ) -> None:
        self.skill_id = skill_id
        self.reason = reason
        self.code = code
        super().__init__(f"{code} skill {skill_id!r}: {reason}")


@runtime_checkable
class SkillResolverProtocol(Protocol):
    """Resolve a stable skill id to a local V2.1 skill root directory."""

    def resolve_skill(self, skill_id: str) -> str | Path:
        """Return the local skill root for ``skill_id``."""


def validate_skill_id(skill_id: str) -> None:
    """Validate the public skill-id grammar shared by specs and runtime."""

    if not isinstance(skill_id, str) or not SKILL_ID_RE.fullmatch(skill_id):
        raise SkillResolutionError(
            str(skill_id),
            "skill id must match " + SKILL_ID_PATTERN,
            code="[F-v3-invalid-skill-id]",
        )


def resolve_skill_root(
    resolver: SkillResolverProtocol,
    skill_id: str,
) -> Path:
    """Resolve and validate that a skill id points at a V2.1 skill root."""

    validate_skill_id(skill_id)
    try:
        root = Path(resolver.resolve_skill(skill_id))
    except SkillResolutionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SkillResolutionError(skill_id, str(exc)) from exc

    if not root.is_dir():
        raise SkillResolutionError(skill_id, f"resolved path is not a directory: {root}")
    if not (root / "GRAPH.md").is_file():
        raise SkillResolutionError(skill_id, f"resolved path has no GRAPH.md: {root}")
    return root


__all__ = [
    "SKILL_ID_PATTERN",
    "SKILL_ID_RE",
    "SkillResolutionError",
    "SkillResolverProtocol",
    "resolve_skill_root",
    "validate_skill_id",
]
