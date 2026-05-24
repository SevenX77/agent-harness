"""Studio implementation of the engine SkillResolverProtocol."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.skill_resolver_protocol import (
    SkillResolutionError,
    SkillResolverProtocol,
    validate_skill_id,
)

from app.core.adapters.metadata_local import LocalJsonMetadataStore


class StudioSkillResolver(SkillResolverProtocol):
    """Resolve V0.3.0 skill ids through the Studio local skill registry."""

    def __init__(self, metadata: LocalJsonMetadataStore) -> None:
        self._metadata = metadata

    def resolve_skill(self, skill_id: str) -> Path:
        """Return a registered graph skill root or raise SkillResolutionError."""
        validate_skill_id(skill_id)
        try:
            return self._metadata.resolve_registered_skill_path(skill_id)
        except FileNotFoundError as exc:
            raise SkillResolutionError(
                skill_id,
                "skill is not registered in Studio skill registry",
                code="[F-v3-skill-not-registered]",
            ) from exc
        except Exception as exc:
            raise SkillResolutionError(
                skill_id,
                str(exc),
                code="[F-v3-skill-not-registered]",
            ) from exc


__all__ = ["StudioSkillResolver"]
