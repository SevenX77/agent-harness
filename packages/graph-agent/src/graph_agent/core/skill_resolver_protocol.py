"""Skill resolver protocol for V0.3.0 skill-id based composition."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from graph_agent.core.exceptions import ResourceNotFoundError, make_error_payload

SKILL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
SKILL_ID_RE = re.compile(SKILL_ID_PATTERN)


class SkillResolutionError(ResourceNotFoundError):
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
        message = f"skill {skill_id!r}: {reason}"
        super().__init__(message, payload=make_error_payload(code, message, skill_id=skill_id))


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
            code="[F-v3-resolver-skill-id-invalid]",
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
        raise SkillResolutionError(
            skill_id,
            f"resolved path is not a directory: {root}",
            code="[F-v3-resolver-path-invalid]",
        )
    if not (root / "GRAPH.md").is_file():
        raise SkillResolutionError(
            skill_id,
            f"resolved path has no GRAPH.md: {root}",
            code="[F-v3-resolver-path-invalid]",
        )
    return root


def require_skill_resolver(
    resolver: SkillResolverProtocol | None,
    *,
    caller: str,
) -> SkillResolverProtocol:
    """Return resolver or raise the V0.3 resolver-domain missing error."""

    if resolver is None:
        raise SkillResolutionError(
            caller,
            "skill_resolver is required",
            code="[F-v3-resolver-missing]",
        )
    if not callable(getattr(resolver, "resolve_skill", None)):
        # Fail at the boundary: without this, a non-conforming object only
        # explodes as an AttributeError deep inside the first compile that
        # actually needs the resolver (adjudication 2026-08-19; the spec'd
        # code existed for years with no emitter).
        raise SkillResolutionError(
            caller,
            f"skill_resolver {type(resolver).__name__!r} exposes no callable resolve_skill",
            code="[F-v3-resolver-interface-invalid]",
        )
    return resolver


__all__ = [
    "SKILL_ID_PATTERN",
    "SKILL_ID_RE",
    "SkillResolutionError",
    "SkillResolverProtocol",
    "require_skill_resolver",
    "resolve_skill_root",
    "validate_skill_id",
]
